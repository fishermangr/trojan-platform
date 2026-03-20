## =============================================================================
## Vivado TCL Script: Synthesis, Implementation & Bitstream Generation
## Target: CW312-A35 (XC7A35T-1CPG236C) on CW313 carrier board
##
## Usage:
##   vivado -mode batch -source synthesize.tcl
##   vivado -mode batch -source synthesize.tcl -tclargs --rtl_dir /path/to/rtl
##
## This script:
##   1. Creates an in-memory project targeting the Artix-7 35T
##   2. Reads all Verilog sources (XLS-generated + wrapper RTL)
##   3. Reads the XDC constraints for CW312-A35 / CW313
##   4. Runs synthesis
##   5. Runs implementation (place & route)
##   6. Generates the bitstream
## =============================================================================

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
set script_dir [file dirname [file normalize [info script]]]
set project_root [file normalize [file join $script_dir ".."]]

# Defaults
set rtl_dir    [file join $project_root "rtl"]
set cw_dir     [file join $project_root "rtl" "cw"]
set xdc_file   [file join $script_dir "cw312_a35.xdc"]
set output_dir [file join $project_root "build"]
set part       "xc7a35tcsg324-1"
set top_module "ss2_aes_wrapper"

# Override from command-line -tclargs
for {set i 0} {$i < [llength $argv]} {incr i} {
    set arg [lindex $argv $i]
    switch -- $arg {
        "--rtl_dir"    { incr i; set rtl_dir    [lindex $argv $i] }
        "--xdc_file"   { incr i; set xdc_file   [lindex $argv $i] }
        "--output_dir" { incr i; set output_dir  [lindex $argv $i] }
        "--part"       { incr i; set part        [lindex $argv $i] }
        "--top"        { incr i; set top_module  [lindex $argv $i] }
    }
}

puts "============================================================"
puts " Vivado Synthesis & Implementation for CW312-A35"
puts "============================================================"
puts " RTL dir:    $rtl_dir"
puts " XDC file:   $xdc_file"
puts " Output dir: $output_dir"
puts " Part:       $part"
puts " Top module: $top_module"
puts "============================================================"

# ---------------------------------------------------------------------------
# Create output directory
# ---------------------------------------------------------------------------
file mkdir $output_dir

# ---------------------------------------------------------------------------
# Create in-memory project
# ---------------------------------------------------------------------------
create_project -in_memory -part $part

# ---------------------------------------------------------------------------
# Read Verilog sources
# ---------------------------------------------------------------------------

# CW reference HDL (ss2, uart, crc, fifo, cdc, cw305 register infrastructure)
set cw_files [glob -nocomplain [file join $cw_dir "*.v"]]
foreach f $cw_files {
    puts "  Reading CW: $f"
    read_verilog $f
}

# XLS AES adapter and generated core
set rtl_v_files [glob -nocomplain [file join $rtl_dir "*.v"]]
foreach f $rtl_v_files {
    puts "  Reading RTL: $f"
    read_verilog $f
}
set sv_files [glob -nocomplain [file join $rtl_dir "*.sv"]]
foreach f $sv_files {
    puts "  Reading SV: $f"
    read_verilog -sv $f
}

if {[llength $cw_files] == 0} {
    puts "ERROR: No CW reference files found in $cw_dir"
    exit 1
}
if {[llength $sv_files] == 0} {
    puts "ERROR: No SystemVerilog files found in $rtl_dir (need aes_128.sv)"
    puts "  Run the HLS script first: python3 hls/run_hls.py"
    exit 1
}

# ---------------------------------------------------------------------------
# Read constraints
# ---------------------------------------------------------------------------
if {![file exists $xdc_file]} {
    puts "ERROR: XDC file not found: $xdc_file"
    exit 1
}
puts "  Reading constraints: $xdc_file"
read_xdc $xdc_file

# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------
puts "\n============================================================"
puts " Running Synthesis..."
puts "============================================================"

synth_design -top $top_module -part $part -flatten_hierarchy rebuilt \
    -verilog_define SS2_WRAPPER -verilog_define XLS_AES

# Write post-synthesis checkpoint & reports
write_checkpoint -force [file join $output_dir "${top_module}_synth.dcp"]
report_timing_summary -file [file join $output_dir "timing_synth.rpt"]
report_utilization -file [file join $output_dir "utilization_synth.rpt"]
report_power -file [file join $output_dir "power_synth.rpt"]

puts " Synthesis complete."

# ---------------------------------------------------------------------------
# Implementation: Optimize, Place, Route
# ---------------------------------------------------------------------------
puts "\n============================================================"
puts " Running Implementation..."
puts "============================================================"

# Optimize
opt_design

# Place
place_design
write_checkpoint -force [file join $output_dir "${top_module}_placed.dcp"]
report_timing_summary -file [file join $output_dir "timing_placed.rpt"]

# Physical optimization
phys_opt_design

# Route
route_design
write_checkpoint -force [file join $output_dir "${top_module}_routed.dcp"]

# Post-route reports
report_timing_summary -file [file join $output_dir "timing_routed.rpt"]
report_utilization -file [file join $output_dir "utilization_routed.rpt"]
report_power -file [file join $output_dir "power_routed.rpt"]
report_drc -file [file join $output_dir "drc_routed.rpt"]

puts " Implementation complete."

# ---------------------------------------------------------------------------
# Bitstream Generation
# ---------------------------------------------------------------------------
puts "\n============================================================"
puts " Generating Bitstream..."
puts "============================================================"

write_bitstream -force [file join $output_dir "${top_module}.bit"]

puts "\n============================================================"
puts " BUILD COMPLETE"
puts " Bitstream: [file join $output_dir ${top_module}.bit]"
puts "============================================================"

exit 0
