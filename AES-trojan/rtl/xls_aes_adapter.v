`timescale 1ns / 1ps
`default_nettype none

// Adapter: converts CW305 register start/done interface to XLS ready/valid channels.
// On a 'start' pulse, latches key and plaintext, asserts vld signals to the XLS core,
// and waits for ciphertext_out_vld. Then captures ciphertext and pulses 'done'.

module xls_aes_adapter (
    input  wire         clk,
    input  wire         rst,

    // CW305 register interface (from cw305_reg_aes)
    input  wire [127:0] key,
    input  wire [127:0] plaintext,
    input  wire         start,       // one-cycle pulse
    output reg  [127:0] ciphertext,
    output reg          done,        // one-cycle pulse when result ready
    output wire         busy,
    output wire         ready
);

    // XLS aes_128 channel interface
    wire [127:0] xls_ct_out;
    wire         xls_ct_out_vld;
    wire         xls_key_in_rdy;
    wire         xls_pt_in_rdy;

    reg          xls_key_in_vld;
    reg          xls_pt_in_vld;
    reg          xls_ct_out_rdy;
    reg  [127:0] key_reg;
    reg  [127:0] pt_reg;

    localparam S_IDLE    = 3'd0;
    localparam S_LOAD    = 3'd1;
    localparam S_WAIT_K  = 3'd2;
    localparam S_WAIT_P  = 3'd3;
    localparam S_WAIT_CT = 3'd4;
    localparam S_DONE    = 3'd5;

    reg [2:0] state;

    assign busy  = (state != S_IDLE);
    assign ready = (state == S_IDLE);

    always @(posedge clk) begin
        if (rst) begin
            state          <= S_IDLE;
            done           <= 1'b0;
            xls_key_in_vld <= 1'b0;
            xls_pt_in_vld  <= 1'b0;
            xls_ct_out_rdy <= 1'b0;
            ciphertext     <= 128'b0;
        end else begin
            done <= 1'b0;

            case (state)
                S_IDLE: begin
                    xls_key_in_vld <= 1'b0;
                    xls_pt_in_vld  <= 1'b0;
                    xls_ct_out_rdy <= 1'b0;
                    if (start) begin
                        key_reg <= key;
                        pt_reg  <= plaintext;
                        state   <= S_LOAD;
                    end
                end

                S_LOAD: begin
                    // Assert both valid signals
                    xls_key_in_vld <= 1'b1;
                    xls_pt_in_vld  <= 1'b1;
                    xls_ct_out_rdy <= 1'b1;
                    state <= S_WAIT_K;
                end

                S_WAIT_K: begin
                    // Wait for key accepted
                    if (xls_key_in_rdy && xls_key_in_vld)
                        xls_key_in_vld <= 1'b0;
                    // Wait for plaintext accepted
                    if (xls_pt_in_rdy && xls_pt_in_vld)
                        xls_pt_in_vld <= 1'b0;
                    // Both accepted?
                    if ((xls_key_in_rdy || !xls_key_in_vld) &&
                        (xls_pt_in_rdy  || !xls_pt_in_vld))
                        state <= S_WAIT_CT;
                end

                S_WAIT_CT: begin
                    xls_key_in_vld <= 1'b0;
                    xls_pt_in_vld  <= 1'b0;
                    xls_ct_out_rdy <= 1'b1;
                    if (xls_ct_out_vld) begin
                        ciphertext     <= xls_ct_out;
                        xls_ct_out_rdy <= 1'b0;
                        state          <= S_DONE;
                    end
                end

                S_DONE: begin
                    done  <= 1'b1;
                    state <= S_IDLE;
                end

                default: state <= S_IDLE;
            endcase
        end
    end

    aes_128 u_aes_128 (
        .clk                (clk),
        .rst                (rst),
        .key_in             (key_reg),
        .key_in_vld         (xls_key_in_vld),
        .key_in_rdy         (xls_key_in_rdy),
        .plaintext_in       (pt_reg),
        .plaintext_in_vld   (xls_pt_in_vld),
        .plaintext_in_rdy   (xls_pt_in_rdy),
        .ciphertext_out     (xls_ct_out),
        .ciphertext_out_vld (xls_ct_out_vld),
        .ciphertext_out_rdy (xls_ct_out_rdy)
    );

endmodule

`default_nettype wire
