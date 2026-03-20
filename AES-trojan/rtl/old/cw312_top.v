// CW312-A35 Top-Level Wrapper for AES-128 ECB
//
// This module wraps the XLS-generated AES-128 core with:
//   - SimpleSerial v1.1 protocol over UART
//   - Trigger pulse generation for ChipWhisperer Husky power analysis
//   - Clock and reset management
//
// SimpleSerial v1.1 Commands:
//   'k' + 32 hex chars + '\n' : Load 128-bit key
//   'p' + 32 hex chars + '\n' : Encrypt plaintext, returns 'r' + 32 hex chars + '\n'
//
// Pin mapping (CW312-A35 on CW313 carrier):
//   clk_in   : HS1 clock from ChipWhisperer Husky (~7.37 MHz)
//   uart_rxd : IO1 (serial data from Husky to FPGA)
//   uart_txd : IO2 (serial data from FPGA to Husky)
//   trig_out : IO4 (trigger output to Husky — active high during encryption)

module cw312_top #(
    parameter CLKS_PER_BIT = 192,  // 7_370_000 / 38400 ≈ 192
    parameter BAUD_RATE    = 38400
)(
    input  wire clk_in,
    input  wire uart_rxd,
    output wire uart_txd,
    output wire trig_out,
    output wire led1,
    output wire led2,
    output wire led3
);

    // =========================================================================
    // Reset generator (simple power-on reset)
    // =========================================================================
    reg [7:0] rst_cnt = 8'd0;
    reg       rst     = 1'b1;

    always @(posedge clk_in) begin
        if (rst_cnt < 8'd255) begin
            rst_cnt <= rst_cnt + 1;
            rst     <= 1'b1;
        end else begin
            rst <= 1'b0;
        end
    end

    // =========================================================================
    // UART RX
    // =========================================================================
    wire [7:0] rx_byte;
    wire       rx_done;

    uart_rx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_uart_rx (
        .clk          (clk_in),
        .rst          (rst),
        .i_rx_serial  (uart_rxd),
        .o_rx_byte    (rx_byte),
        .o_rx_done    (rx_done)
    );

    // =========================================================================
    // UART TX
    // =========================================================================
    reg  [7:0] tx_byte;
    reg        tx_start;
    wire       tx_busy;
    wire       tx_done;

    uart_tx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_uart_tx (
        .clk          (clk_in),
        .rst          (rst),
        .i_tx_byte    (tx_byte),
        .i_tx_start   (tx_start),
        .o_tx_serial  (uart_txd),
        .o_tx_busy    (tx_busy),
        .o_tx_done    (tx_done)
    );

    // =========================================================================
    // Hex ASCII conversion functions
    // =========================================================================
    // Convert ASCII hex character to 4-bit nibble
    function [3:0] hex_to_nibble;
        input [7:0] ascii;
        begin
            if (ascii >= 8'h30 && ascii <= 8'h39)       // '0'-'9'
                hex_to_nibble = ascii[3:0];
            else if (ascii >= 8'h41 && ascii <= 8'h46)   // 'A'-'F'
                hex_to_nibble = ascii[3:0] + 4'd9;
            else if (ascii >= 8'h61 && ascii <= 8'h66)   // 'a'-'f'
                hex_to_nibble = ascii[3:0] + 4'd9;
            else
                hex_to_nibble = 4'h0;
        end
    endfunction

    // Convert 4-bit nibble to ASCII hex character
    function [7:0] nibble_to_hex;
        input [3:0] nibble;
        begin
            if (nibble < 4'd10)
                nibble_to_hex = 8'h30 + {4'h0, nibble};  // '0'-'9'
            else
                nibble_to_hex = 8'h61 + {4'h0, nibble} - 8'd10; // 'a'-'f'
        end
    endfunction

    // =========================================================================
    // SimpleSerial State Machine
    // =========================================================================
    localparam SS_IDLE          = 4'd0;
    localparam SS_CMD           = 4'd1;
    localparam SS_RX_DATA       = 4'd2;
    localparam SS_RX_NEWLINE    = 4'd3;
    localparam SS_ENCRYPT       = 4'd4;
    localparam SS_ENCRYPT_WAIT  = 4'd5;
    localparam SS_TX_RESP_HDR   = 4'd6;
    localparam SS_TX_RESP_DATA  = 4'd7;
    localparam SS_TX_NEWLINE    = 4'd8;
    localparam SS_TX_WAIT       = 4'd9;

    reg [3:0]    ss_state;
    reg [7:0]    cmd_type;        // 'k' or 'p'
    reg [127:0]  key_reg;         // Stored key
    reg [127:0]  pt_reg;          // Plaintext input
    reg [127:0]  ct_reg;          // Ciphertext output
    reg [5:0]    hex_count;       // Count of hex chars received (0..31)
    reg [5:0]    tx_hex_count;    // Count of hex chars sent
    reg          trigger;         // Trigger signal

    assign trig_out = trigger;

    // LED indicators
    assign led1 = ~rst;          // LED1: power-on (active after reset)
    assign led2 = trigger;       // LED2: encryption in progress
    assign led3 = (ss_state == SS_IDLE); // LED3: idle

    // =========================================================================
    // AES-128 Combinational Core (instantiate XLS-generated module)
    // The XLS-generated module has ready/valid channel interfaces.
    // For simplicity, we drive it combinationally: present inputs, latch output.
    // =========================================================================

    // AES core connections — directly compute the cipher
    // We implement a simple FSM that feeds data to the AES core and reads back.
    //
    // The XLS-generated module interface (pipeline_stages=1):
    //   input  wire        clk,
    //   input  wire        rst,
    //   input  wire [127:0] key_in,
    //   input  wire        key_in_vld,
    //   output wire        key_in_rdy,
    //   input  wire [127:0] plaintext_in,
    //   input  wire        plaintext_in_vld,
    //   output wire        plaintext_in_rdy,
    //   output wire [127:0] ciphertext_out,
    //   output wire        ciphertext_out_vld,
    //   input  wire        ciphertext_out_rdy

    reg         aes_key_vld;
    reg         aes_pt_vld;
    wire        aes_key_rdy;
    wire        aes_pt_rdy;
    wire [127:0] aes_ct;
    wire        aes_ct_vld;
    reg         aes_ct_rdy;

    aes_128 u_aes_core (
        .clk                (clk_in),
        .rst                (rst),
        .key_in             (key_reg),
        .key_in_vld         (aes_key_vld),
        .key_in_rdy         (aes_key_rdy),
        .plaintext_in       (pt_reg),
        .plaintext_in_vld   (aes_pt_vld),
        .plaintext_in_rdy   (aes_pt_rdy),
        .ciphertext_out     (aes_ct),
        .ciphertext_out_vld (aes_ct_vld),
        .ciphertext_out_rdy (aes_ct_rdy)
    );

    // =========================================================================
    // Main FSM
    // =========================================================================
    always @(posedge clk_in) begin
        if (rst) begin
            ss_state     <= SS_IDLE;
            cmd_type     <= 8'd0;
            key_reg      <= 128'd0;
            pt_reg       <= 128'd0;
            ct_reg       <= 128'd0;
            hex_count    <= 6'd0;
            tx_hex_count <= 6'd0;
            trigger      <= 1'b0;
            tx_start     <= 1'b0;
            tx_byte      <= 8'd0;
            aes_key_vld  <= 1'b0;
            aes_pt_vld   <= 1'b0;
            aes_ct_rdy   <= 1'b0;
        end else begin
            tx_start <= 1'b0;

            case (ss_state)
                // ---------------------------------------------------------
                // IDLE: Wait for command character
                // ---------------------------------------------------------
                SS_IDLE: begin
                    trigger     <= 1'b0;
                    aes_key_vld <= 1'b0;
                    aes_pt_vld  <= 1'b0;
                    aes_ct_rdy  <= 1'b0;
                    if (rx_done) begin
                        cmd_type  <= rx_byte;
                        hex_count <= 6'd0;
                        if (rx_byte == 8'h6B || rx_byte == 8'h70) begin
                            // 'k' (0x6B) or 'p' (0x70)
                            ss_state <= SS_RX_DATA;
                        end
                        // Ignore unknown commands
                    end
                end

                // ---------------------------------------------------------
                // RX_DATA: Receive 32 hex characters (128 bits)
                // ---------------------------------------------------------
                SS_RX_DATA: begin
                    if (rx_done) begin
                        if (rx_byte == 8'h0A || rx_byte == 8'h0D) begin
                            // Newline received early — process what we have
                            if (cmd_type == 8'h6B) begin
                                // 'k' command — key loaded
                                ss_state <= SS_IDLE;
                            end else begin
                                // 'p' command — start encryption
                                ss_state <= SS_ENCRYPT;
                            end
                        end else begin
                            // Shift in hex nibble
                            if (cmd_type == 8'h6B) begin
                                key_reg <= {key_reg[123:0], hex_to_nibble(rx_byte)};
                            end else begin
                                pt_reg <= {pt_reg[123:0], hex_to_nibble(rx_byte)};
                            end
                            hex_count <= hex_count + 1;
                            if (hex_count == 6'd31) begin
                                ss_state <= SS_RX_NEWLINE;
                            end
                        end
                    end
                end

                // ---------------------------------------------------------
                // RX_NEWLINE: Wait for newline after 32 hex chars
                // ---------------------------------------------------------
                SS_RX_NEWLINE: begin
                    if (rx_done) begin
                        if (cmd_type == 8'h6B) begin
                            ss_state <= SS_IDLE;
                        end else begin
                            ss_state <= SS_ENCRYPT;
                        end
                    end
                end

                // ---------------------------------------------------------
                // ENCRYPT: Assert trigger and present data to AES core
                // ---------------------------------------------------------
                SS_ENCRYPT: begin
                    trigger     <= 1'b1;
                    aes_key_vld <= 1'b1;
                    aes_pt_vld  <= 1'b1;
                    aes_ct_rdy  <= 1'b1;
                    ss_state    <= SS_ENCRYPT_WAIT;
                end

                // ---------------------------------------------------------
                // ENCRYPT_WAIT: Wait for AES core to produce valid output
                // ---------------------------------------------------------
                SS_ENCRYPT_WAIT: begin
                    aes_ct_rdy <= 1'b1;
                    if (aes_ct_vld) begin
                        ct_reg       <= aes_ct;
                        trigger      <= 1'b0;
                        aes_key_vld  <= 1'b0;
                        aes_pt_vld   <= 1'b0;
                        aes_ct_rdy   <= 1'b0;
                        tx_hex_count <= 6'd0;
                        ss_state     <= SS_TX_RESP_HDR;
                    end
                end

                // ---------------------------------------------------------
                // TX_RESP_HDR: Send 'r' response header
                // ---------------------------------------------------------
                SS_TX_RESP_HDR: begin
                    if (!tx_busy) begin
                        tx_byte  <= 8'h72;  // 'r'
                        tx_start <= 1'b1;
                        ss_state <= SS_TX_WAIT;
                    end
                end

                // ---------------------------------------------------------
                // TX_RESP_DATA: Send 32 hex characters of ciphertext
                // ---------------------------------------------------------
                SS_TX_RESP_DATA: begin
                    if (!tx_busy) begin
                        // Send MSB nibble first: ct_reg[127:124], [123:120], ...
                        tx_byte  <= nibble_to_hex(ct_reg[127:124]);
                        tx_start <= 1'b1;
                        ct_reg   <= {ct_reg[123:0], 4'b0000};
                        tx_hex_count <= tx_hex_count + 1;
                        ss_state <= SS_TX_WAIT;
                    end
                end

                // ---------------------------------------------------------
                // TX_NEWLINE: Send newline to terminate response
                // ---------------------------------------------------------
                SS_TX_NEWLINE: begin
                    if (!tx_busy) begin
                        tx_byte  <= 8'h0A;  // '\n'
                        tx_start <= 1'b1;
                        ss_state <= SS_TX_WAIT;
                    end
                end

                // ---------------------------------------------------------
                // TX_WAIT: Wait for UART TX to finish, then advance
                // ---------------------------------------------------------
                SS_TX_WAIT: begin
                    if (tx_done) begin
                        if (ss_state == SS_TX_WAIT) begin
                            // Determine next state based on context
                            if (tx_byte == 8'h72) begin
                                // Just sent 'r', now send data
                                ss_state <= SS_TX_RESP_DATA;
                            end else if (tx_byte == 8'h0A) begin
                                // Just sent newline, done
                                ss_state <= SS_IDLE;
                            end else if (tx_hex_count >= 6'd32) begin
                                // All 32 hex chars sent, send newline
                                ss_state <= SS_TX_NEWLINE;
                            end else begin
                                // More hex chars to send
                                ss_state <= SS_TX_RESP_DATA;
                            end
                        end
                    end
                end

                default: ss_state <= SS_IDLE;
            endcase
        end
    end

endmodule
