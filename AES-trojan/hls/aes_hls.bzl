"""
Bazel build rules for AES-128 HLS using Google XLS.

These rules can be used within the XLS Bazel workspace to build
the AES-128 design as part of the XLS build system.

Usage (from the XLS workspace root):
  1. Symlink or copy this file and the src/ directory into the XLS tree
  2. Create a BUILD file that loads these rules
  3. Run: bazel build //path/to:aes_128_verilog

Alternatively, use the standalone run_hls.py script which invokes the
XLS tools directly without Bazel.
"""

def aes_hls_rules(
        name = "aes_128",
        src = "//AES-trojan/src:aes_xls.cc",
        hdr = "//AES-trojan/src:aes_xls.h",
        top_class = "AesEcb128Encrypt",
        pipeline_stages = 1,
        clock_period_ps = 135685):
    """
    Define Bazel build targets for the AES-128 XLS HLS flow.

    Args:
        name: Base name for generated targets.
        src: Label for the C++ source file.
        hdr: Label for the C++ header file.
        top_class: Top-level class name for xlscc.
        pipeline_stages: Number of pipeline stages for codegen.
        clock_period_ps: Target clock period in picoseconds.
    """

    # Step 1: xlscc — C++ to XLS IR
    ir_name = name + "_ir"
    block_pb_name = name + "_block_pb"
    native.genrule(
        name = ir_name,
        srcs = [src, hdr],
        outs = [name + ".ir", name + ".block.pbtxt", name + ".sig.textproto"],
        cmd = """
            $(location //xls/contrib/xlscc) \
                $(location {src}) \
                -I$$(dirname $(location {hdr})) \
                -I$(GENDIR)/xls/contrib/xlscc/synth_only \
                --top={top_class} \
                --block_from_class \
                --block_pb_out=$(location {name}.block.pbtxt) \
                --meta_out=$(location {name}.sig.textproto) \
                --out=$(location {name}.ir)
        """.format(src = src, hdr = hdr, top_class = top_class, name = name),
        tools = ["//xls/contrib/xlscc"],
    )

    # Step 2: opt_main — Optimize IR
    opt_ir_name = name + "_opt_ir"
    native.genrule(
        name = opt_ir_name,
        srcs = [":" + ir_name],
        outs = [name + ".opt.ir"],
        cmd = """
            $(location //xls/tools:opt_main) \
                $(location {name}.ir) \
                --output=$(location {name}.opt.ir)
        """.format(name = name),
        tools = ["//xls/tools:opt_main"],
    )

    # Step 3: codegen_main — Generate Verilog
    verilog_name = name + "_verilog"
    native.genrule(
        name = verilog_name,
        srcs = [":" + opt_ir_name],
        outs = [name + ".v", name + ".schedule.textproto"],
        cmd = """
            $(location //xls/tools:codegen_main) \
                $(location {name}.opt.ir) \
                --output_verilog_path=$(location {name}.v) \
                --generator=pipeline \
                --pipeline_stages={stages} \
                --clock_period_ps={clock_ps} \
                --delay_model=unit \
                --reset=rst \
                --reset_active_low=false \
                --reset_data_path=true \
                --module_name={name} \
                --output_schedule_path=$(location {name}.schedule.textproto)
        """.format(
            name = name,
            stages = pipeline_stages,
            clock_ps = clock_period_ps,
        ),
        tools = ["//xls/tools:codegen_main"],
    )
