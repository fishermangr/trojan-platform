## CW312-A35 (XC7A35T-1CSG324) on CW313 Carrier Board
## Pin constraints for AES-128 SCA target design using SS2 wrapper
##
## Reference: Official NewAE xc7a35_ss.xdc from
## https://github.com/newaetech/chipwhisperer/blob/develop/firmware/fpgas/aes/vivado/xc7a35_ss.xdc
## Top module: ss2_aes_wrapper

######## HARDWARE ON BOARD

# LEDs
set_property -dict { DRIVE 8 IOSTANDARD LVCMOS33 PACKAGE_PIN R1 } [get_ports led1]
set_property -dict { DRIVE 8 IOSTANDARD LVCMOS33 PACKAGE_PIN V2 } [get_ports led2]
set_property -dict { DRIVE 8 IOSTANDARD LVCMOS33 PACKAGE_PIN V5 } [get_ports led3]

# clocks
set_property -dict { IOSTANDARD LVCMOS33 PACKAGE_PIN A13 } [get_ports clkout]
set_property -dict { IOSTANDARD LVCMOS33 PACKAGE_PIN D15 } [get_ports clk]
create_clock -period 135.685 -name clk -waveform {0.000 67.843} [get_nets clk]

# IO1-4
set_property -dict { IOSTANDARD LVCMOS33 PACKAGE_PIN V10 } [get_ports txd]
set_property -dict { IOSTANDARD LVCMOS33 PACKAGE_PIN V11 } [get_ports rxd]
set_property -dict { IOSTANDARD LVCMOS33 PACKAGE_PIN V12 } [get_ports io3]
set_property -dict { IOSTANDARD LVCMOS33 PACKAGE_PIN V14 } [get_ports io4]

# misc pins
set_property -dict { IOSTANDARD LVCMOS33 PACKAGE_PIN A16 } [get_ports resetn]

# pull downs
set_property PULLTYPE PULLDOWN [get_ports io3]

# input delays
set_input_delay -clock clk 0.000 [get_ports rxd]
set_input_delay -clock clk 0.000 [get_ports io3]
set_false_path -from [get_ports rxd]
set_false_path -from [get_ports io3]
set_false_path -from [get_ports resetn]

# output delays
set_output_delay -clock clk 0.000 [get_ports LED*]
set_output_delay -clock clk 0.000 [get_ports txd]
set_output_delay -clock clk 0.000 [get_ports io4]
set_output_delay -clock clk 0.000 [get_ports clkout]
set_false_path -to [get_ports LED*]
set_false_path -to [get_ports txd]
set_false_path -to [get_ports io4]
set_false_path -to [get_ports clkout]

set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
