/*
 * Verification-record authentication (Mode A, device side).
 *
 * IMPORTANT: authenticating a record is NOT checking mathematics. A valid signature only
 * shows that a trusted host produced this exact record. What the host actually did is
 * stated in the record's `mode` field:
 *   LOCAL_KERNEL     the signing host ran the Lean kernel on the named theorem itself
 *   EXTERNAL_REPORT  the signing host only relays results reported by others
 * The device shows EXTERNAL_REPORT records as INCOMPLETE, never as VALID.
 *
 * Record wire format: canonical JSON object (ASCII, flat; string values plus one string
 * array `axioms`), signed with Ed25519 over  "RHPC-RECORD-v1\n" || json_bytes.
 * Pure C99; same file on device and host.
 */
#ifndef RHPC_RECORD_H
#define RHPC_RECORD_H

#include <stddef.h>
#include <stdint.h>

#define RHPC_REC_MAX_JSON   2048u
#define RHPC_REC_MAX_FIELD  160u
#define RHPC_REC_MAX_AXIOMS 8u

typedef enum {
    /* VALID */
    RHPC_REC_AUTHENTIC_LOCAL_VERIFIED = 0,
    /* INCOMPLETE */
    RHPC_REC_AUTHENTIC_EXTERNAL,      /* authentic, but maths only externally reported */
    RHPC_REC_INCOMPLETE,              /* outcome INCOMPLETE or NOT_RUN */
    /* UNTRUSTED */
    RHPC_REC_UNTRUSTED_KEY,
    RHPC_REC_UNKNOWN_STATEMENT,       /* theorem not in the device's pinned table */
    /* INVALID */
    RHPC_REC_INVALID_SIGNATURE,
    RHPC_REC_MALFORMED,
    RHPC_REC_STATEMENT_MISMATCH,      /* statement fingerprint differs from the pinned one */
    RHPC_REC_NONSTANDARD_AXIOMS,
    RHPC_REC_REPORTS_FAILURE,         /* outcome FAILED */
    RHPC_REC__COUNT
} rhpc_rec_status_t;

typedef enum { RHPC_REC_CAT_VALID, RHPC_REC_CAT_INCOMPLETE, RHPC_REC_CAT_UNTRUSTED, RHPC_REC_CAT_INVALID } rhpc_rec_cat_t;

typedef struct {
    const char    *key_id;        /* 16 hex chars: first 8 bytes of the public key */
    const uint8_t *public_key;    /* 32 bytes */
    const char    *label;
} rhpc_trusted_key_t;

typedef struct {
    const char *theorem;          /* exact Lean name */
    const char *statement_fp;     /* 64 hex chars */
    const char *method;           /* how the fingerprint was computed */
} rhpc_pinned_statement_t;

typedef struct {
    char schema[RHPC_REC_MAX_FIELD], key_id[RHPC_REC_MAX_FIELD], theorem[RHPC_REC_MAX_FIELD];
    char statement_fp[RHPC_REC_MAX_FIELD], source_sha256[RHPC_REC_MAX_FIELD], checker[RHPC_REC_MAX_FIELD];
    char mode[RHPC_REC_MAX_FIELD], outcome[RHPC_REC_MAX_FIELD], timestamp[RHPC_REC_MAX_FIELD];
    char note[RHPC_REC_MAX_FIELD];
    char axioms[RHPC_REC_MAX_AXIOMS][RHPC_REC_MAX_FIELD];
    unsigned n_axioms;
    uint32_t seen;                /* bitmask of fields present */
} rhpc_record_t;

typedef struct {
    rhpc_rec_status_t status;
    const char       *detail;     /* static string: which check decided */
    rhpc_record_t     rec;        /* parsed fields (valid if status != MALFORMED) */
} rhpc_rec_result_t;

/* Parse a record without checking the signature (exposed for tests). 0 = ok. */
int rhpc_record_parse(const char *json, size_t len, rhpc_record_t *out, const char **why);

/* Full verification: parse, key lookup, Ed25519 signature, statement pin, axioms, outcome. */
rhpc_rec_status_t rhpc_record_verify(const char *json, size_t json_len, const uint8_t sig[64],
                                     const rhpc_trusted_key_t *keys, size_t n_keys,
                                     const rhpc_pinned_statement_t *pins, size_t n_pins,
                                     rhpc_rec_result_t *res);

rhpc_rec_cat_t rhpc_record_category(rhpc_rec_status_t s);
const char    *rhpc_record_status_name(rhpc_rec_status_t s);
const char    *rhpc_record_category_name(rhpc_rec_cat_t c);

#endif
