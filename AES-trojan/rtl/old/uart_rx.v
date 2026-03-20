// UART Receiver Module
// Configurable baud rate via CLKS_PER_BIT parameter.
// 8-N-1 format: 8 data bits, no parity, 1 stop bit.
//
// Outputs:
//   o_rx_byte  - received byte (valid when o_rx_done pulses)
//   o_rx_done  - single-cycle pulse when a byte is received

module uart_rx #(
    parameter CLKS_PER_BIT = 192  // 7.37 MHz / 38400 baud ≈ 192
)(
    input  wire       clk,
    input  wire       rst,
    input  wire       i_rx_serial,
    output reg  [7:0] o_rx_byte,
    output reg        o_rx_done
);

    localparam IDLE     = 3'd0;
    localparam START    = 3'd1;
    localparam DATA     = 3'd2;
    localparam STOP     = 3'd3;
    localparam CLEANUP  = 3'd4;

    reg [2:0]  state;
    reg [15:0] clk_count;
    reg [2:0]  bit_index;
    reg [7:0]  rx_data;
    reg        rx_serial_r1;
    reg        rx_serial_r2;

    // Double-register the input for metastability
    always @(posedge clk) begin
        if (rst) begin
            rx_serial_r1 <= 1'b1;
            rx_serial_r2 <= 1'b1;
        end else begin
            rx_serial_r1 <= i_rx_serial;
            rx_serial_r2 <= rx_serial_r1;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            state     <= IDLE;
            clk_count <= 0;
            bit_index <= 0;
            o_rx_done <= 1'b0;
            o_rx_byte <= 8'h00;
            rx_data   <= 8'h00;
        end else begin
            o_rx_done <= 1'b0;

            case (state)
                IDLE: begin
                    clk_count <= 0;
                    bit_index <= 0;
                    if (rx_serial_r2 == 1'b0) begin
                        state <= START;
                    end
                end

                START: begin
                    if (clk_count == (CLKS_PER_BIT - 1) / 2) begin
                        if (rx_serial_r2 == 1'b0) begin
                            clk_count <= 0;
                            state     <= DATA;
                        end else begin
                            state <= IDLE;
                        end
                    end else begin
                        clk_count <= clk_count + 1;
                    end
                end

                DATA: begin
                    if (clk_count < CLKS_PER_BIT - 1) begin
                        clk_count <= clk_count + 1;
                    end else begin
                        clk_count        <= 0;
                        rx_data[bit_index] <= rx_serial_r2;
                        if (bit_index < 7) begin
                            bit_index <= bit_index + 1;
                        end else begin
                            bit_index <= 0;
                            state     <= STOP;
                        end
                    end
                end

                STOP: begin
                    if (clk_count < CLKS_PER_BIT - 1) begin
                        clk_count <= clk_count + 1;
                    end else begin
                        o_rx_done <= 1'b1;
                        o_rx_byte <= rx_data;
                        clk_count <= 0;
                        state     <= CLEANUP;
                    end
                end

                CLEANUP: begin
                    state <= IDLE;
                end

                default: state <= IDLE;
            endcase
        end
    end

endmodule
