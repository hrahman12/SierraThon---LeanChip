/* Host build of the device checker: the same firmware/src/rhpc_checker.c, unmodified.
 *
 *   rhpc_host check <file>...        verdict per file: ACCEPT | REJECT_MALFORMED | REJECT_INVALID | REJECT_RESOURCE
 *   rhpc_host bench <iters> <file>   checks/s and inference steps/s on this host
 */
#define _POSIX_C_SOURCE 199309L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "rhpc_checker.h"

static rhpc_ctx_t ctx;   /* static, like on the device */

static size_t read_file(const char *path, uint8_t *buf, size_t cap, int *too_big) {
    FILE *f = fopen(path, "rb");
    if (!f) { perror(path); exit(2); }
    size_t n = fread(buf, 1, cap, f);
    *too_big = (n == cap && fgetc(f) != EOF);
    fclose(f);
    return n;
}

static const char *cls_name(rhpc_class_t c) {
    switch (c) {
    case RHPC_CLASS_ACCEPT: return "ACCEPT";
    case RHPC_CLASS_MALFORMED: return "REJECT_MALFORMED";
    case RHPC_CLASS_INVALID: return "REJECT_INVALID";
    default: return "REJECT_RESOURCE";
    }
}

int main(int argc, char **argv) {
    static uint8_t buf[RHPC_MAX_CERT_BYTES * 4];
    if (argc >= 3 && strcmp(argv[1], "check") == 0) {
        for (int i = 2; i < argc; i++) {
            int big;
            size_t n = read_file(argv[i], buf, sizeof buf, &big);
            rhpc_result_t r;
            /* An over-long file is passed with its true length so the size limit triggers. */
            rhpc_check(&ctx, buf, big ? sizeof buf + 1 : n, &r, NULL, NULL);
            printf("%s\t%s\t%s\tstep=%d\tsteps=%u\tnodes=%u\n", argv[i], cls_name(rhpc_classify(r.err)),
                   rhpc_err_name(r.err), (int)r.step, (unsigned)r.steps_checked, (unsigned)r.nodes_used);
        }
        return 0;
    }
    if (argc == 4 && strcmp(argv[1], "bench") == 0) {
        long iters = atol(argv[2]);
        int big;
        size_t n = read_file(argv[3], buf, sizeof buf, &big);
        rhpc_result_t r;
        struct timespec t0, t1;
        clock_gettime(CLOCK_MONOTONIC, &t0);
        for (long k = 0; k < iters; k++) rhpc_check(&ctx, buf, n, &r, NULL, NULL);
        clock_gettime(CLOCK_MONOTONIC, &t1);
        double s = (t1.tv_sec - t0.tv_sec) + (t1.tv_nsec - t0.tv_nsec) / 1e9;
        printf("{\"file\":\"%s\",\"result\":\"%s\",\"bytes\":%zu,\"steps\":%u,\"nodes\":%u,"
               "\"iters\":%ld,\"seconds\":%.6f,\"us_per_check\":%.4f,\"steps_per_s\":%.0f}\n",
               argv[3], rhpc_err_name(r.err), n, (unsigned)r.steps_checked, (unsigned)r.nodes_used, iters, s,
               s / iters * 1e6, (double)r.steps_checked * iters / s);
        return 0;
    }
    fprintf(stderr, "usage: rhpc_host check <file>... | rhpc_host bench <iters> <file>\n");
    return 2;
}
