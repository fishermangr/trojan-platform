#!/usr/bin/env python3
"""
HLS Script for AES-128 using Google XLS (xlscc).

This script runs the full XLS HLS pipeline:
  1. xlscc:        C++ -> XLS IR
  2. opt_main:     XLS IR -> Optimized XLS IR
  3. codegen_main: Optimized XLS IR -> Verilog RTL

Usage:
  python3 run_hls.py [--xls-root /path/to/xls] [--output-dir ../rtl]

The generated Verilog will be placed in the output directory, ready for
Vivado synthesis.
"""

import argparse
import os
import subprocess
import sys
import shutil


def find_xls_root():
    """Auto-detect XLS root directory."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.normpath(os.path.join(script_dir, "..", "..", "xls"))
    if os.path.isdir(candidate) and os.path.isfile(
        os.path.join(candidate, "bazel-bin", "xls", "contrib", "xlscc", "xlscc")
    ):
        return candidate
    return None


def run_cmd(cmd, description, dry_run=False):
    """Run a shell command with logging."""
    print(f"\n{'=' * 60}")
    print(f"[HLS] {description}")
    print(f"  CMD: {' '.join(cmd)}")
    print(f"{'=' * 60}")
    if dry_run:
        print("  (dry run — skipped)")
        return 0
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        print(f"[HLS] ERROR: {description} failed with exit code {result.returncode}")
        sys.exit(result.returncode)
    print(f"[HLS] {description} — OK")
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description="Run Google XLS HLS pipeline for AES-128"
    )
    parser.add_argument(
        "--xls-root",
        default=None,
        help="Path to the XLS repository root (auto-detected if omitted)",
    )
    parser.add_argument(
        "--src-dir",
        default=None,
        help="Path to the AES XLS source directory (default: ../src relative to this script)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for generated RTL output (default: ../rtl)",
    )
    parser.add_argument(
        "--top-func",
        default="AesEcb128Encrypt",
        help="Top-level class name for xlscc (default: AesEcb128Encrypt)",
    )
    parser.add_argument(
        "--pipeline-stages",
        type=int,
        default=1,
        help="Number of pipeline stages for codegen (default: 1 = combinational)",
    )
    parser.add_argument(
        "--clock-period-ps",
        type=int,
        default=135685,
        help="Target clock period in picoseconds for codegen (default: 135685 = ~7.37 MHz)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them",
    )
    args = parser.parse_args()

    # Resolve paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.normpath(os.path.join(script_dir, ".."))

    xls_root = args.xls_root or find_xls_root()
    if xls_root is None:
        print("[HLS] ERROR: Cannot find XLS root. Use --xls-root to specify it.")
        sys.exit(1)
    xls_root = os.path.abspath(xls_root)

    src_dir = args.src_dir or os.path.join(project_root, "src")
    output_dir = args.output_dir or os.path.join(project_root, "rtl")
    os.makedirs(output_dir, exist_ok=True)

    # XLS tool paths
    xlscc = os.path.join(xls_root, "bazel-bin", "xls", "contrib", "xlscc", "xlscc")
    opt_main = os.path.join(xls_root, "bazel-bin", "xls", "tools", "opt_main")
    codegen_main = os.path.join(xls_root, "bazel-bin", "xls", "tools", "codegen_main")

    for tool, name in [(xlscc, "xlscc"), (opt_main, "opt_main"), (codegen_main, "codegen_main")]:
        if not os.path.isfile(tool):
            print(f"[HLS] ERROR: {name} not found at {tool}")
            print(f"  Build it with: cd {xls_root} && bazel build //xls/contrib/xlscc //xls/tools:opt_main //xls/tools:codegen_main")
            sys.exit(1)

    # Source file
    src_file = os.path.join(src_dir, "aes_xls.cc")
    if not os.path.isfile(src_file):
        print(f"[HLS] ERROR: Source file not found: {src_file}")
        sys.exit(1)

    # XLS synth_only include path (for xls_int.h)
    xlscc_include = os.path.join(xls_root, "xls", "contrib", "xlscc", "synth_only")

    # Find Bazel external cache root (needed for ac_types headers used by xls_int.h)
    # xls_int.h includes "external/com_github_hlslibs_ac_types/include/ac_int.h"
    # which resolves relative to the Bazel cache external root.
    bazel_external_root = None
    import glob as _glob
    candidates = _glob.glob(os.path.expanduser(
        "~/.cache/bazel/_bazel_*/*/external/com_github_hlslibs_ac_types/include/ac_int.h"
    ))
    if candidates:
        # The include root is two directories above "external/..."
        bazel_external_root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(candidates[0])
        )))
        print(f"[HLS] Bazel ext root: {bazel_external_root}")
    else:
        print("[HLS] WARNING: Could not find ac_types in Bazel cache.")
        print("  xls_int.h may fail to resolve. Try: bazel build //xls/contrib/xlscc")

    # Output file paths
    ir_file = os.path.join(output_dir, "aes_128.ir")
    opt_ir_file = os.path.join(output_dir, "aes_128.opt.ir")
    verilog_file = os.path.join(output_dir, "aes_128.sv")
    schedule_file = os.path.join(output_dir, "aes_128.schedule.textproto")
    block_file = os.path.join(output_dir, "aes_128.block.textproto")
    signature_file = os.path.join(output_dir, "aes_128.sig.textproto")

    print(f"[HLS] XLS root:    {xls_root}")
    print(f"[HLS] Source:      {src_file}")
    print(f"[HLS] Output dir:  {output_dir}")
    print(f"[HLS] Top class:   {args.top_func}")

    # -------------------------------------------------------------------------
    # Step 1: xlscc — C++ to XLS IR
    # -------------------------------------------------------------------------
    include_dirs = [xlscc_include, src_dir]
    if bazel_external_root:
        include_dirs.append(bazel_external_root)

    xlscc_cmd = [
        xlscc,
        src_file,
        f"--include_dirs={','.join(include_dirs)}",
        f"--defines=__SYNTHESIS__",
        f"--top={args.top_func}",
        f"--block_from_class={args.top_func}",
        f"--block_pb={block_file}",
        f"--block_pb_text",
        f"--meta_out={signature_file}",
        f"--meta_out_text",
        f"--out={ir_file}",
    ]
    run_cmd(xlscc_cmd, "xlscc: C++ → XLS IR", args.dry_run)

    # -------------------------------------------------------------------------
    # Step 2: opt_main — Optimize IR
    # -------------------------------------------------------------------------
    opt_cmd = [
        opt_main,
        ir_file,
        f"--output_path={opt_ir_file}",
    ]
    run_cmd(opt_cmd, "opt_main: Optimize XLS IR", args.dry_run)

    # -------------------------------------------------------------------------
    # Step 3: codegen_main — Generate Verilog
    # -------------------------------------------------------------------------
    codegen_cmd = [
        codegen_main,
        opt_ir_file,
        f"--output_verilog_path={verilog_file}",
        f"--generator=pipeline",
        f"--pipeline_stages={args.pipeline_stages}",
        f"--clock_period_ps={args.clock_period_ps}",
        f"--delay_model=unit",
        f"--reset=rst",
        f"--reset_active_low=false",
        f"--reset_data_path=true",
        f"--module_name=aes_128",
        f"--output_schedule_path={schedule_file}",
    ]
    run_cmd(codegen_cmd, "codegen_main: XLS IR → Verilog", args.dry_run)

    print(f"\n{'=' * 60}")
    print(f"[HLS] HLS pipeline complete!")
    print(f"  Verilog:     {verilog_file}")
    print(f"  Schedule:    {schedule_file}")
    print(f"  Block proto: {block_file}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
