# Host build and golden-vector tests for the portable estimator core.
# No vendor toolchain is needed.

# make's built-in default is CC=cc; on this machine a broken `cc` shim
# shadows the compiler, so reassign unless the caller set CC explicitly.
ifeq ($(origin CC),default)
CC = gcc
endif
CFLAGS  ?= -std=c99 -Wall -Wextra -O2 -fPIC
PY      ?= python3

ROOT    := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))../..
MIRROR  := $(ROOT)/frequency_estimator_firmware/host/freq_est_mirror.py
VECTORS := $(ROOT)/frequency_estimator_firmware/host/vectors/manifest.json

all: libfreq_est.so libfreq_est_fixed.so

SRCS := freq_est.c fft_est.c zc_est.c

libfreq_est.so: $(SRCS) freq_est.h
	$(CC) $(CFLAGS) -shared $(SRCS) -o $@ -lm

libfreq_est_fixed.so: $(SRCS) freq_est.h
	$(CC) $(CFLAGS) -DFE_FIXED_POINT -shared $(SRCS) -o $@ -lm

# Regenerate golden vectors only if the manifest is missing.
$(VECTORS):
	$(PY) $(ROOT)/frequency_estimator_firmware/host/export_golden_vectors.py

test: all $(VECTORS)
	$(PY) $(ROOT)/frequency_estimator_firmware/host/run_host_tests.py
	$(MAKE) sanitize-fixed

sanitize-fixed:
	@out=$$(mktemp /tmp/ece455-fixed-bounds.XXXXXX); \
	$(CC) $(CFLAGS) -O1 -g -DFE_FIXED_POINT \
		-fsanitize=address,undefined -fno-omit-frame-pointer \
		-I. $(ROOT)/frequency_estimator_firmware/host/test_fixed_bounds.c \
		$(SRCS) -o $$out -lm; \
	rc=$$?; if [ $$rc -eq 0 ]; then $$out; rc=$$?; fi; \
	rm -f $$out; exit $$rc

clean:
	rm -f libfreq_est.so libfreq_est_fixed.so

.PHONY: test sanitize-fixed clean
