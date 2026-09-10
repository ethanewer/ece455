# Host build + tests for the portable estimator core (C1/C2/C3).
# `make` builds both numeric modes; `make test` runs the host suite
# (golden vectors + sensitivity matrix). No vendor toolchain needed.

# make's built-in default is CC=cc; on this machine a broken `cc` shim
# shadows the compiler, so reassign unless the caller set CC explicitly.
ifeq ($(origin CC),default)
CC = gcc
endif
CFLAGS  ?= -std=c99 -Wall -Wextra -O2 -fPIC
PY      ?= python3

ROOT    := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))../..
MIRROR  := $(ROOT)/tools/freq_est_mirror.py
VECTORS := $(ROOT)/firmware/host/vectors/manifest.json

all: libfreq_est.so libfreq_est_fixed.so

libfreq_est.so: freq_est.c freq_est.h
	$(CC) $(CFLAGS) -shared freq_est.c -o $@ -lm

libfreq_est_fixed.so: freq_est.c freq_est.h
	$(CC) $(CFLAGS) -DFE_FIXED_POINT -shared freq_est.c -o $@ -lm

# Regenerate golden vectors only if the manifest is missing.
$(VECTORS):
	$(PY) $(ROOT)/tools/export_golden_vectors.py

test: all $(VECTORS)
	$(PY) $(ROOT)/firmware/host/run_host_tests.py
	$(PY) $(ROOT)/firmware/host/sensitivity_score.py

clean:
	rm -f libfreq_est.so libfreq_est_fixed.so

.PHONY: test clean
