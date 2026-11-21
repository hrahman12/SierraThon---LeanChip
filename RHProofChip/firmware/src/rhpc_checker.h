/*
 * RHPC on-device proof checker (Mode B).
 *
 * Checks certificates in the RHP1 binary format (docs/CERTIFICATE_FORMAT.md) for the
 * calculus formalised in lean/RHProofChip/Calculus.lean. The inference rules are exactly
 * `stepResult` in lean/RHProofChip/Checker.lean; Lean proves that `check` is sound.
 *
 * Differences from the Lean reference, all of which can only cause *extra rejections*:
 *   - fixed resource limits (bytes, nodes, lines, nesting depth) -> RHPC_E_RESOURCE_*
 *   - formulas are hash-consed so structural equality is an index comparison
 *
 * No dynamic allocation. All state lives in a caller-provided rhpc_ctx_t.
 * Pure C99, no SDK dependencies: the same file is compiled for the RP2040 and the host.
 */
#ifndef RHPC_CHECKER_H
#define RHPC_CHECKER_H

#include <stddef.h>
#include <stdint.h>

#define RHPC_MAX_CERT_BYTES 4096u
#define RHPC_MAX_NODES      1024u
#define RHPC_MAX_LINES      256u
#define RHPC_MAX_DEPTH      48u
#define RHPC_HASH_SLOTS     2048u   /* power of two, > 2 * RHPC_MAX_NODES */

typedef enum {
    RHPC_OK = 0,
    /* malformed certificate (the Lean decoder also rejects these) */
    RHPC_E_MAGIC,
    RHPC_E_TRUNCATED,
    RHPC_E_TRAILING,
    RHPC_E_TAG,
    /* invalid proof (the Lean checker also rejects these) */
    RHPC_E_INDEX,          /* reference to a line that does not exist yet */
    RHPC_E_RULE,           /* premise has the wrong shape / does not match */
    RHPC_E_GOAL,           /* last line is not the goal */
    RHPC_E_EMPTY,          /* no steps */
    /* resource limits (device-only; the Lean reference has no limits) */
    RHPC_E_RESOURCE_SIZE,
    RHPC_E_RESOURCE_NODES,
    RHPC_E_RESOURCE_LINES,
    RHPC_E_RESOURCE_DEPTH,
    RHPC_E_ARG,            /* NULL pointer etc. */
    RHPC_ERR__COUNT
} rhpc_err_t;

typedef enum { RHPC_CLASS_ACCEPT, RHPC_CLASS_MALFORMED, RHPC_CLASS_INVALID, RHPC_CLASS_RESOURCE } rhpc_class_t;

typedef struct {
    uint8_t  kind;    /* rhpc node kind */
    uint8_t  var;     /* variable number for VAR */
    uint16_t a, b;    /* child node indices */
} rhpc_node_t;

typedef struct {
    rhpc_node_t nodes[RHPC_MAX_NODES];
    uint16_t    hash[RHPC_HASH_SLOTS];   /* node index + 1, 0 = empty */
    uint16_t    lines[RHPC_MAX_LINES];   /* node index of each proved line */
    uint16_t    n_nodes;
    uint16_t    n_lines;
} rhpc_ctx_t;

typedef struct {
    rhpc_err_t err;
    int32_t    step;         /* index of the failing step, -1 if not step-specific */
    uint32_t   steps_total;  /* declared number of steps */
    uint32_t   steps_checked;
    uint32_t   nodes_used;
    uint32_t   bytes;
} rhpc_result_t;

/* Optional progress callback, called after each accepted step (may be NULL). */
typedef void (*rhpc_progress_fn)(uint32_t done, uint32_t total, void *user);

/* Check a certificate. Deterministic: same bytes -> same result. */
rhpc_err_t rhpc_check(rhpc_ctx_t *ctx, const uint8_t *buf, size_t len, rhpc_result_t *res,
                      rhpc_progress_fn progress, void *user);

rhpc_class_t rhpc_classify(rhpc_err_t e);
const char  *rhpc_err_name(rhpc_err_t e);

#endif
