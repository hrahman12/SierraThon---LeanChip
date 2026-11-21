/* Verification-record authentication. See rhpc_record.h. */
#include "rhpc_record.h"

#include <string.h>

#include "monocypher-ed25519.h"

#define DOMAIN "RHPC-RECORD-v1\n"

enum { F_SCHEMA, F_KEY, F_THM, F_FP, F_SRC, F_CHECKER, F_MODE, F_OUTCOME, F_TS, F_NOTE, F_AXIOMS, F__N };
static const char *const FIELD[F__N] = {"schema", "key_id", "theorem", "statement_fp", "source_sha256",
                                        "checker", "mode", "outcome", "timestamp", "note", "axioms"};
#define REQUIRED ((1u << F__N) - 1u - (1u << F_NOTE))

typedef struct { const char *p, *end; } lex_t;

static void ws(lex_t *l) {
    while (l->p < l->end && (*l->p == ' ' || *l->p == '\n' || *l->p == '\r' || *l->p == '\t')) l->p++;
}

static int lit(lex_t *l, char c) {
    ws(l);
    if (l->p < l->end && *l->p == c) { l->p++; return 1; }
    return 0;
}

/* JSON string -> out (NUL-terminated). Printable ASCII only; escapes \" \\ \/ only. */
static int str(lex_t *l, char *out, size_t cap) {
    size_t n = 0;
    if (!lit(l, '"')) return 0;
    while (l->p < l->end) {
        char c = *l->p++;
        if (c == '"') { out[n] = 0; return 1; }
        if (c == '\\') {
            if (l->p >= l->end) return 0;
            c = *l->p++;
            if (c != '"' && c != '\\' && c != '/') return 0;
        } else if ((unsigned char)c < 0x20 || (unsigned char)c > 0x7e) {
            return 0;
        }
        if (n + 1 >= cap) return 0;
        out[n++] = c;
    }
    return 0;
}

static char *slot(rhpc_record_t *r, int f) {
    switch (f) {
    case F_SCHEMA: return r->schema;   case F_KEY: return r->key_id;     case F_THM: return r->theorem;
    case F_FP: return r->statement_fp; case F_SRC: return r->source_sha256; case F_CHECKER: return r->checker;
    case F_MODE: return r->mode;       case F_OUTCOME: return r->outcome; case F_TS: return r->timestamp;
    case F_NOTE: return r->note;       default: return 0;
    }
}

static int is_hex64(const char *s) {
    size_t n = strlen(s);
    if (n != 64) return 0;
    for (size_t i = 0; i < n; i++)
        if (!((s[i] >= '0' && s[i] <= '9') || (s[i] >= 'a' && s[i] <= 'f'))) return 0;
    return 1;
}

int rhpc_record_parse(const char *json, size_t len, rhpc_record_t *r, const char **why) {
    static const char *dummy;
    if (!why) why = &dummy;
    memset(r, 0, sizeof *r);
    if (!json || len == 0 || len > RHPC_REC_MAX_JSON) { *why = "size"; return -1; }
    lex_t l = {json, json + len};
    char key[32];
    if (!lit(&l, '{')) { *why = "expected {"; return -1; }
    if (lit(&l, '}')) { *why = "empty object"; return -1; }
    do {
        if (!str(&l, key, sizeof key)) { *why = "bad key"; return -1; }
        if (!lit(&l, ':')) { *why = "expected :"; return -1; }
        int f = -1;
        for (int i = 0; i < F__N; i++) if (strcmp(key, FIELD[i]) == 0) f = i;
        if (f < 0) { *why = "unknown field"; return -1; }
        if (r->seen & (1u << f)) { *why = "duplicate field"; return -1; }
        r->seen |= 1u << f;
        if (f == F_AXIOMS) {
            if (!lit(&l, '[')) { *why = "axioms must be an array"; return -1; }
            if (!lit(&l, ']')) {
                do {
                    if (r->n_axioms >= RHPC_REC_MAX_AXIOMS) { *why = "too many axioms"; return -1; }
                    if (!str(&l, r->axioms[r->n_axioms++], RHPC_REC_MAX_FIELD)) { *why = "bad axiom"; return -1; }
                } while (lit(&l, ','));
                if (!lit(&l, ']')) { *why = "expected ]"; return -1; }
            }
        } else if (!str(&l, slot(r, f), RHPC_REC_MAX_FIELD)) {
            *why = "bad string value"; return -1;
        }
    } while (lit(&l, ','));
    if (!lit(&l, '}')) { *why = "expected }"; return -1; }
    ws(&l);
    if (l.p != l.end) { *why = "trailing bytes"; return -1; }
    if ((r->seen & REQUIRED) != REQUIRED) { *why = "missing field"; return -1; }
    if (strcmp(r->schema, "rhpc-record/1") != 0) { *why = "schema"; return -1; }
    if (!is_hex64(r->statement_fp) || !is_hex64(r->source_sha256)) { *why = "hash format"; return -1; }
    if (strlen(r->key_id) != 16) { *why = "key_id format"; return -1; }
    *why = "ok";
    return 0;
}

static int in_set(const char *s, const char *const *set, size_t n) {
    for (size_t i = 0; i < n; i++) if (strcmp(s, set[i]) == 0) return 1;
    return 0;
}

static rhpc_rec_status_t done(rhpc_rec_result_t *res, rhpc_rec_status_t s, const char *d) {
    res->status = s;
    res->detail = d;
    return s;
}

rhpc_rec_status_t rhpc_record_verify(const char *json, size_t json_len, const uint8_t sig[64],
                                     const rhpc_trusted_key_t *keys, size_t n_keys,
                                     const rhpc_pinned_statement_t *pins, size_t n_pins,
                                     rhpc_rec_result_t *res) {
    static uint8_t msg[sizeof(DOMAIN) - 1 + RHPC_REC_MAX_JSON];
    const char *why;
    memset(res, 0, sizeof *res);
    if (!sig || rhpc_record_parse(json, json_len, &res->rec, &why) != 0)
        return done(res, RHPC_REC_MALFORMED, why);

    const rhpc_trusted_key_t *k = 0;
    for (size_t i = 0; i < n_keys; i++) if (strcmp(keys[i].key_id, res->rec.key_id) == 0) k = &keys[i];
    if (!k) return done(res, RHPC_REC_UNTRUSTED_KEY, "key_id not in trusted list");

    memcpy(msg, DOMAIN, sizeof(DOMAIN) - 1);
    memcpy(msg + sizeof(DOMAIN) - 1, json, json_len);
    if (crypto_ed25519_check(sig, k->public_key, msg, sizeof(DOMAIN) - 1 + json_len) != 0)
        return done(res, RHPC_REC_INVALID_SIGNATURE, "Ed25519 signature check failed");

    /* From here on the record is authentic. Now judge what it *claims*. */
    const rhpc_pinned_statement_t *pin = 0;
    for (size_t i = 0; i < n_pins; i++) if (strcmp(pins[i].theorem, res->rec.theorem) == 0) pin = &pins[i];
    if (!pin) return done(res, RHPC_REC_UNKNOWN_STATEMENT, "theorem not pinned on device");
    if (strcmp(pin->statement_fp, res->rec.statement_fp) != 0)
        return done(res, RHPC_REC_STATEMENT_MISMATCH, "statement fingerprint differs from pinned statement");

    static const char *const STD_AXIOMS[] = {"propext", "Classical.choice", "Quot.sound"};
    for (unsigned i = 0; i < res->rec.n_axioms; i++)
        if (!in_set(res->rec.axioms[i], STD_AXIOMS, 3))
            return done(res, RHPC_REC_NONSTANDARD_AXIOMS, "axiom outside {propext, Classical.choice, Quot.sound}");

    if (strcmp(res->rec.outcome, "FAILED") == 0) return done(res, RHPC_REC_REPORTS_FAILURE, "record reports FAILED");
    if (strcmp(res->rec.outcome, "INCOMPLETE") == 0 || strcmp(res->rec.outcome, "NOT_RUN") == 0)
        return done(res, RHPC_REC_INCOMPLETE, "record reports INCOMPLETE/NOT_RUN");
    if (strcmp(res->rec.outcome, "VERIFIED") != 0) return done(res, RHPC_REC_MALFORMED, "unknown outcome");

    if (strcmp(res->rec.mode, "LOCAL_KERNEL") == 0)
        return done(res, RHPC_REC_AUTHENTIC_LOCAL_VERIFIED, "authentic; signer ran the Lean kernel itself");
    if (strcmp(res->rec.mode, "EXTERNAL_REPORT") == 0)
        return done(res, RHPC_REC_AUTHENTIC_EXTERNAL, "authentic; maths only externally reported");
    return done(res, RHPC_REC_MALFORMED, "unknown mode");
}

rhpc_rec_cat_t rhpc_record_category(rhpc_rec_status_t s) {
    switch (s) {
    case RHPC_REC_AUTHENTIC_LOCAL_VERIFIED: return RHPC_REC_CAT_VALID;
    case RHPC_REC_AUTHENTIC_EXTERNAL: case RHPC_REC_INCOMPLETE: return RHPC_REC_CAT_INCOMPLETE;
    case RHPC_REC_UNTRUSTED_KEY: case RHPC_REC_UNKNOWN_STATEMENT: return RHPC_REC_CAT_UNTRUSTED;
    default: return RHPC_REC_CAT_INVALID;
    }
}

const char *rhpc_record_status_name(rhpc_rec_status_t s) {
    static const char *const n[RHPC_REC__COUNT] = {
        "AUTHENTIC_LOCAL_VERIFIED", "AUTHENTIC_EXTERNAL", "INCOMPLETE", "UNTRUSTED_KEY", "UNKNOWN_STATEMENT",
        "INVALID_SIGNATURE", "MALFORMED", "STATEMENT_MISMATCH", "NONSTANDARD_AXIOMS", "REPORTS_FAILURE"};
    return (s >= 0 && s < RHPC_REC__COUNT) ? n[s] : "UNKNOWN";
}

const char *rhpc_record_category_name(rhpc_rec_cat_t c) {
    static const char *const n[] = {"VALID", "INCOMPLETE", "UNTRUSTED", "INVALID"};
    return (c >= 0 && c <= RHPC_REC_CAT_INVALID) ? n[c] : "?";
}
