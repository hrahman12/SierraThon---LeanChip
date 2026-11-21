/* RHPC on-device proof checker. See rhpc_checker.h. */
#include "rhpc_checker.h"

#include <string.h>

enum {
    K_VAR = 1, K_BOT = 2, K_IMP = 3, K_EQ = 4,          /* formulas (same as wire tags) */
    K_ZERO = 0x10, K_SUCC = 0x11, K_ADD = 0x12, K_MUL = 0x13  /* terms */
};

enum {
    S_K = 0x20, S_S, S_DNE, S_MP, S_REFL, S_ADDZ, S_ADDS, S_MULZ, S_MULS,
    S_SYMM, S_TRANS, S_CONGS, S_CONGADD, S_CONGMUL
};

#define NONE 0xFFFFu

typedef struct {
    rhpc_ctx_t   *c;
    const uint8_t *p, *end;
    rhpc_err_t    err;     /* first error, RHPC_OK while fine */
    int           intern;  /* 0 = syntax-only mode (after a rule error) */
} parser_t;

static void fail(parser_t *ps, rhpc_err_t e) {
    if (ps->err == RHPC_OK) ps->err = e;
}

static int get_u8(parser_t *ps, uint8_t *out) {
    if (ps->p >= ps->end) { fail(ps, RHPC_E_TRUNCATED); return 0; }
    *out = *ps->p++;
    return 1;
}

static int get_u16(parser_t *ps, uint16_t *out) {
    uint8_t lo, hi;
    if (!get_u8(ps, &lo) || !get_u8(ps, &hi)) return 0;
    *out = (uint16_t)(lo | ((uint16_t)hi << 8));
    return 1;
}

/* ---------- hash-consed node pool ---------- */

static uint32_t node_hash(uint8_t kind, uint8_t var, uint16_t a, uint16_t b) {
    uint32_t h = 2166136261u;                 /* FNV-1a over the 6 node bytes */
    const uint8_t bytes[6] = {kind, var, (uint8_t)a, (uint8_t)(a >> 8), (uint8_t)b, (uint8_t)(b >> 8)};
    for (int i = 0; i < 6; i++) { h ^= bytes[i]; h *= 16777619u; }
    return h;
}

/* Returns the unique index of node (kind,var,a,b), creating it if needed; NONE on exhaustion. */
static uint16_t mk(parser_t *ps, uint8_t kind, uint8_t var, uint16_t a, uint16_t b) {
    if (!ps->intern) return 0;               /* syntax-only mode: value unused */
    rhpc_ctx_t *c = ps->c;
    uint32_t slot = node_hash(kind, var, a, b) & (RHPC_HASH_SLOTS - 1u);
    for (uint32_t probe = 0; probe < RHPC_HASH_SLOTS; probe++) {
        uint16_t e = c->hash[slot];
        if (e == 0) {
            if (c->n_nodes >= RHPC_MAX_NODES) { fail(ps, RHPC_E_RESOURCE_NODES); return NONE; }
            uint16_t idx = c->n_nodes++;
            c->nodes[idx].kind = kind; c->nodes[idx].var = var;
            c->nodes[idx].a = a; c->nodes[idx].b = b;
            c->hash[slot] = (uint16_t)(idx + 1u);
            return idx;
        }
        const rhpc_node_t *n = &c->nodes[e - 1u];
        if (n->kind == kind && n->var == var && n->a == a && n->b == b) return (uint16_t)(e - 1u);
        slot = (slot + 1u) & (RHPC_HASH_SLOTS - 1u);
    }
    fail(ps, RHPC_E_RESOURCE_NODES);
    return NONE;
}

/* ---------- recursive-descent parsers (depth-bounded) ---------- */

static uint16_t p_term(parser_t *ps, unsigned depth) {
    uint8_t tag;
    if (depth > RHPC_MAX_DEPTH) { fail(ps, RHPC_E_RESOURCE_DEPTH); return NONE; }
    if (!get_u8(ps, &tag)) return NONE;
    switch (tag) {
    case K_ZERO: return mk(ps, K_ZERO, 0, 0, 0);
    case K_SUCC: {
        uint16_t t = p_term(ps, depth + 1);
        if (ps->err) return NONE;
        return mk(ps, K_SUCC, 0, t, 0);
    }
    case K_ADD: case K_MUL: {
        uint16_t a = p_term(ps, depth + 1);
        if (ps->err) return NONE;
        uint16_t b = p_term(ps, depth + 1);
        if (ps->err) return NONE;
        return mk(ps, tag, 0, a, b);
    }
    default: fail(ps, RHPC_E_TAG); return NONE;
    }
}

static uint16_t p_formula(parser_t *ps, unsigned depth) {
    uint8_t tag;
    if (depth > RHPC_MAX_DEPTH) { fail(ps, RHPC_E_RESOURCE_DEPTH); return NONE; }
    if (!get_u8(ps, &tag)) return NONE;
    switch (tag) {
    case K_VAR: {
        uint8_t v;
        if (!get_u8(ps, &v)) return NONE;
        return mk(ps, K_VAR, v, 0, 0);
    }
    case K_BOT: return mk(ps, K_BOT, 0, 0, 0);
    case K_IMP: {
        uint16_t a = p_formula(ps, depth + 1);
        if (ps->err) return NONE;
        uint16_t b = p_formula(ps, depth + 1);
        if (ps->err) return NONE;
        return mk(ps, K_IMP, 0, a, b);
    }
    case K_EQ: {
        uint16_t a = p_term(ps, depth + 1);
        if (ps->err) return NONE;
        uint16_t b = p_term(ps, depth + 1);
        if (ps->err) return NONE;
        return mk(ps, K_EQ, 0, a, b);
    }
    default: fail(ps, RHPC_E_TAG); return NONE;
    }
}

/* ---------- inference rules (mirror Lean's stepResult) ---------- */

static const rhpc_node_t *N(const rhpc_ctx_t *c, uint16_t i) { return &c->nodes[i]; }

/* Fetch an earlier line; returns 0 and sets INDEX error if it does not exist. */
static int line(parser_t *ps, uint16_t i, uint16_t *out) {
    if (i >= ps->c->n_lines) { fail(ps, RHPC_E_INDEX); return 0; }
    *out = ps->c->lines[i];
    return 1;
}

/* Parse and apply one step. Returns the new line's node, or NONE (ps->err set). */
static uint16_t p_step(parser_t *ps) {
    uint8_t op;
    uint16_t a, b, c3, i, j, li, lj;
    if (!get_u8(ps, &op)) return NONE;
    switch (op) {
    case S_K:
        a = p_formula(ps, 1); if (ps->err) return NONE;
        b = p_formula(ps, 1); if (ps->err) return NONE;
        return mk(ps, K_IMP, 0, a, mk(ps, K_IMP, 0, b, a));
    case S_S: {
        a = p_formula(ps, 1); if (ps->err) return NONE;
        b = p_formula(ps, 1); if (ps->err) return NONE;
        c3 = p_formula(ps, 1); if (ps->err) return NONE;
        uint16_t bc = mk(ps, K_IMP, 0, b, c3), abc = mk(ps, K_IMP, 0, a, bc);
        uint16_t ab = mk(ps, K_IMP, 0, a, b), ac = mk(ps, K_IMP, 0, a, c3);
        uint16_t rhs = mk(ps, K_IMP, 0, ab, ac);
        return mk(ps, K_IMP, 0, abc, rhs);
    }
    case S_DNE: {
        a = p_formula(ps, 1); if (ps->err) return NONE;
        uint16_t bot = mk(ps, K_BOT, 0, 0, 0);
        uint16_t na = mk(ps, K_IMP, 0, a, bot), nna = mk(ps, K_IMP, 0, na, bot);
        return mk(ps, K_IMP, 0, nna, a);
    }
    case S_REFL:
        a = p_term(ps, 1); if (ps->err) return NONE;
        return mk(ps, K_EQ, 0, a, a);
    case S_ADDZ:
        a = p_term(ps, 1); if (ps->err) return NONE;
        return mk(ps, K_EQ, 0, mk(ps, K_ADD, 0, a, mk(ps, K_ZERO, 0, 0, 0)), a);
    case S_ADDS: {
        a = p_term(ps, 1); if (ps->err) return NONE;
        b = p_term(ps, 1); if (ps->err) return NONE;
        uint16_t lhs = mk(ps, K_ADD, 0, a, mk(ps, K_SUCC, 0, b, 0));
        uint16_t rhs = mk(ps, K_SUCC, 0, mk(ps, K_ADD, 0, a, b), 0);
        return mk(ps, K_EQ, 0, lhs, rhs);
    }
    case S_MULZ: {
        a = p_term(ps, 1); if (ps->err) return NONE;
        uint16_t z = mk(ps, K_ZERO, 0, 0, 0);
        return mk(ps, K_EQ, 0, mk(ps, K_MUL, 0, a, z), z);
    }
    case S_MULS: {
        a = p_term(ps, 1); if (ps->err) return NONE;
        b = p_term(ps, 1); if (ps->err) return NONE;
        uint16_t lhs = mk(ps, K_MUL, 0, a, mk(ps, K_SUCC, 0, b, 0));
        uint16_t rhs = mk(ps, K_ADD, 0, mk(ps, K_MUL, 0, a, b), a);
        return mk(ps, K_EQ, 0, lhs, rhs);
    }
    case S_MP:
        if (!get_u16(ps, &i) || !get_u16(ps, &j)) return NONE;
        if (!ps->intern) return 0;
        if (!line(ps, i, &li) || !line(ps, j, &lj)) return NONE;
        if (N(ps->c, li)->kind != K_IMP || N(ps->c, li)->a != lj) { fail(ps, RHPC_E_RULE); return NONE; }
        return N(ps->c, li)->b;
    case S_SYMM:
        if (!get_u16(ps, &i)) return NONE;
        if (!ps->intern) return 0;
        if (!line(ps, i, &li)) return NONE;
        if (N(ps->c, li)->kind != K_EQ) { fail(ps, RHPC_E_RULE); return NONE; }
        return mk(ps, K_EQ, 0, N(ps->c, li)->b, N(ps->c, li)->a);
    case S_TRANS:
        if (!get_u16(ps, &i) || !get_u16(ps, &j)) return NONE;
        if (!ps->intern) return 0;
        if (!line(ps, i, &li) || !line(ps, j, &lj)) return NONE;
        if (N(ps->c, li)->kind != K_EQ || N(ps->c, lj)->kind != K_EQ ||
            N(ps->c, li)->b != N(ps->c, lj)->a) { fail(ps, RHPC_E_RULE); return NONE; }
        return mk(ps, K_EQ, 0, N(ps->c, li)->a, N(ps->c, lj)->b);
    case S_CONGS:
        if (!get_u16(ps, &i)) return NONE;
        if (!ps->intern) return 0;
        if (!line(ps, i, &li)) return NONE;
        if (N(ps->c, li)->kind != K_EQ) { fail(ps, RHPC_E_RULE); return NONE; }
        return mk(ps, K_EQ, 0, mk(ps, K_SUCC, 0, N(ps->c, li)->a, 0), mk(ps, K_SUCC, 0, N(ps->c, li)->b, 0));
    case S_CONGADD: case S_CONGMUL: {
        if (!get_u16(ps, &i) || !get_u16(ps, &j)) return NONE;
        if (!ps->intern) return 0;
        if (!line(ps, i, &li) || !line(ps, j, &lj)) return NONE;
        if (N(ps->c, li)->kind != K_EQ || N(ps->c, lj)->kind != K_EQ) { fail(ps, RHPC_E_RULE); return NONE; }
        uint8_t k = (op == S_CONGADD) ? K_ADD : K_MUL;
        uint16_t l = mk(ps, k, 0, N(ps->c, li)->a, N(ps->c, lj)->a);
        uint16_t r = mk(ps, k, 0, N(ps->c, li)->b, N(ps->c, lj)->b);
        return mk(ps, K_EQ, 0, l, r);
    }
    default:
        fail(ps, RHPC_E_TAG);
        return NONE;
    }
}

rhpc_err_t rhpc_check(rhpc_ctx_t *ctx, const uint8_t *buf, size_t len, rhpc_result_t *res,
                      rhpc_progress_fn progress, void *user) {
    rhpc_result_t local;
    if (!res) res = &local;
    memset(res, 0, sizeof *res);
    res->step = -1;
    res->bytes = (uint32_t)len;
    if (!ctx || (!buf && len)) { res->err = RHPC_E_ARG; return res->err; }
    if (len > RHPC_MAX_CERT_BYTES) { res->err = RHPC_E_RESOURCE_SIZE; return res->err; }

    memset(ctx->hash, 0, sizeof ctx->hash);
    ctx->n_nodes = 0;
    ctx->n_lines = 0;

    parser_t ps = {ctx, buf, buf + len, RHPC_OK, 1};
    if (len < 4 || memcmp(buf, "RHP1", 4) != 0) { res->err = RHPC_E_MAGIC; return res->err; }
    ps.p += 4;

    uint16_t goal = p_formula(&ps, 1);
    uint16_t nsteps = 0;
    if (!ps.err) get_u16(&ps, &nsteps);
    res->steps_total = nsteps;

    rhpc_err_t rule_err = RHPC_OK;
    for (uint32_t s = 0; s < nsteps && !ps.err; s++) {
        uint16_t f = p_step(&ps);
        if (ps.err) {
            rhpc_class_t cl = rhpc_classify(ps.err);
            if (cl == RHPC_CLASS_INVALID && ps.intern) {
                /* Like the Lean reference (decode first, then check): a malformed byte
                   later in the file takes precedence over an invalid step. Continue in
                   syntax-only mode to find out. */
                rule_err = ps.err;
                res->step = (int32_t)s;
                ps.err = RHPC_OK;
                ps.intern = 0;
                continue;
            }
            if (res->step < 0) res->step = (int32_t)s;
            break;
        }
        if (!ps.intern) continue;
        if (ctx->n_lines >= RHPC_MAX_LINES) { fail(&ps, RHPC_E_RESOURCE_LINES); res->step = (int32_t)s; break; }
        ctx->lines[ctx->n_lines++] = f;
        res->steps_checked = s + 1u;
        if (progress) progress(s + 1u, nsteps, user);
    }
    if (!ps.err && ps.p != ps.end) fail(&ps, RHPC_E_TRAILING);

    res->nodes_used = ctx->n_nodes;
    if (ps.err) {
        /* In syntax-only mode node exhaustion cannot happen; a malformed error wins. */
        res->err = ps.err;
        if (rhpc_classify(ps.err) == RHPC_CLASS_MALFORMED) res->step = -1;
        return res->err;
    }
    if (rule_err != RHPC_OK) { res->err = rule_err; return res->err; }
    if (ctx->n_lines == 0) { res->err = RHPC_E_EMPTY; return res->err; }
    if (ctx->lines[ctx->n_lines - 1u] != goal) { res->err = RHPC_E_GOAL; return res->err; }
    res->err = RHPC_OK;
    return RHPC_OK;
}

rhpc_class_t rhpc_classify(rhpc_err_t e) {
    switch (e) {
    case RHPC_OK: return RHPC_CLASS_ACCEPT;
    case RHPC_E_MAGIC: case RHPC_E_TRUNCATED: case RHPC_E_TRAILING: case RHPC_E_TAG:
        return RHPC_CLASS_MALFORMED;
    case RHPC_E_INDEX: case RHPC_E_RULE: case RHPC_E_GOAL: case RHPC_E_EMPTY:
        return RHPC_CLASS_INVALID;
    default:
        return RHPC_CLASS_RESOURCE;
    }
}

const char *rhpc_err_name(rhpc_err_t e) {
    static const char *const names[RHPC_ERR__COUNT] = {
        "OK", "E_MAGIC", "E_TRUNCATED", "E_TRAILING", "E_TAG", "E_INDEX", "E_RULE", "E_GOAL",
        "E_EMPTY", "E_RESOURCE_SIZE", "E_RESOURCE_NODES", "E_RESOURCE_LINES", "E_RESOURCE_DEPTH",
        "E_ARG"};
    return (e >= 0 && e < RHPC_ERR__COUNT) ? names[e] : "E_UNKNOWN";
}
