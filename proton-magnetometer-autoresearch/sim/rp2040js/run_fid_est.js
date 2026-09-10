/*
 * C4 runner: load the SRAM image into rp2040js, start the core from the
 * vector table, capture UART0, assert the reported frequency.
 *
 * Usage: node sim/rp2040js/run_fid_est.js <image.bin> [truth_hz]
 * Exits 0 iff the firmware reports FREQ_MHZ within 500 mHz (0.5 Hz) of
 * the truth.
 *
 * Explicitly NOT a timing/sensitivity oracle: this proves samples move
 * through the firmware estimator (byte-identical freq_est.c), nothing
 * about clock accuracy or jitter.
 */
const fs = require("fs");
const path = require("path");
const { RP2040 } = require("rp2040js");

const imagePath = process.argv[2];
const truthHz = Number(process.argv[3] || 2128.819237);
const TOL_HZ = 0.5;

const image = fs.readFileSync(imagePath);
const rp2040 = new RP2040();
rp2040.sram.set(image, 0);           // link address == 0x20000000

let serial = "";
rp2040.uart[0].onByte = (b) => {
  serial += String.fromCharCode(b);
};

// Start the core from the image's vector table (SP, PC with thumb bit).
const sp = rp2040.sramView.getUint32(0, true);
const pc = rp2040.sramView.getUint32(4, true);
rp2040.core.SP = sp;
rp2040.core.PC = pc | 1;

const core = rp2040.core;
const MAX_INSTRUCTIONS = 8e9;
let n = 0;
let done = false;
while (n < MAX_INSTRUCTIONS && !done) {
  for (let k = 0; k < 100000 && !done; k++) {
    core.executeInstruction();
    n++;
    if (serial.includes("FID-EST-DONE")) {
      done = true;
      break;
    }
  }
}

process.stdout.write(serial);
if (!done) {
  console.error("\n[fid-est] firmware did not finish in time");
  process.exit(2);
}
const m = serial.match(/FREQ_MHZ=(\d+)/);
if (!m) {
  console.error("\n[fid-est] no FREQ_MHZ line in UART output");
  process.exit(1);
}
const reportedHz = Number(m[1]) / 1000;
const errHz = Math.abs(reportedHz - truthHz);
console.log(`\n[fid-est] reported ${reportedHz.toFixed(4)} Hz, ` +
  `truth ${truthHz.toFixed(4)} Hz, err ${errHz.toFixed(4)} Hz ` +
  `(gate ${TOL_HZ} Hz)`);
process.exit(errHz <= TOL_HZ ? 0 : 1);
