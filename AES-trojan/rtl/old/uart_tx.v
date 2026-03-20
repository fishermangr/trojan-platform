// UART Transmitter Module
// Configurable baud rate via CLKS_PER_BIT parameter.
// 8-N-1 format: 8 data bits, no parity, 1 stop bit.
//
// Inputs:
//   i_tx_byte  - byte to transmit
//   i_tx_start - pulse high to begin transmission
// Outputs:
//   o_tx_serial - serial output line
//   o_tx_busy   - high while transmitting
//   o_tx_done   - single-cycle pulse when transmission completes

module uart_tx #(
    parameter CLKS_PER_BIT = 192  // 7.37 MHz / 38400 baud ≈ 192
)(
    input  wire       clk,
    input  wire       rst,
    input  wire [7:0] i_tx_byte,
    input  wire       i_tx_start,
    output reg        o_tx_serial,
    output reg        o_tx_busy,
    output reg        o_tx_done
);

    localparam IDLE  = 3'd0;
    localparam START = 3'd1;
    localparam DATA  = 3'd2;
    localparam STOP  = 3'd3;
    localparam DONE  = 3'd4;

    reg [2:0]  state;
    reg [15:0] clk_count;
    reg [2:0]  bit_index;
    reg [7:0]  tx_data;

    always @(posedge clk) begin
        if (rst) begin
            state       <= IDLE;
            clk_count   <= 0;
            bit_index   <= 0;
            o_tx_serial <= 1'b1;
            o_tx_busy   <= 1'b0;
            o_tx_done   <= 1'b0;
            tx_data     <= 8'h00;
        end else begin
            o_tx_done <= 1'b0;

            case (state)
                IDLE: begin
                    o_tx_serial <= 1'b1;
                    o_tx_busy   <= 1'b0;
                    clk_count   <= 0;
                    bit_index   <= 0;
                    if (i_tx_start) begin
                        tx_data   <= i_tx_byte;
                        o_tx_busy <= 1'b1;
                        state     <= START;
                    end
                end

                START: begin
                    o_tx_serial <= 1'b0;  // Start bit
                    if (clk_count < CLKS_PER_BIT - 1) begin
                        clk_count <= clk_count + 1;
                    end else begin
                        clk_count <= 0;
                        state     <= DATA;
                    end
                end

                DATA: begin
                    o_tx_serial <= tx_data[bit_index];
                    if (clk_count < CLKS_PER_BIT - 1) begin
                        clk_count <= clk_count + 1;
                    end else begin
                        clk_count <= 0;
                        if (bit_index < 7) begin
                            bit_index <= bit_index + 1;
                        end else begin
                            bit_index <= 0;
                            state     <= STOP;
                        end
                    end
                end

                STOP: begin
                    o_tx_serial <= 1'b1;  // Stop bit
                    if (clk_count < CLKS_PER_BIT - 1) begin
                        clk_count <= clk_count + 1;
                    end else begin
                        clk_count <= 0;
                        state     <= DONE;
                    end
                end

                DONE: begin
                    o_tx_done <= 1'b1;
                    o_tx_busy <= 1'b0;
                    state     <= IDLE;
                end

                default: state <= IDLE;
            endcase
        end
    end

endmodule
