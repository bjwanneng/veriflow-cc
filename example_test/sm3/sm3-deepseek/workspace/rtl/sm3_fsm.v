//==============================================================================
// sm3_fsm — 3-state control FSM: IDLE -> CALC (64 cycles) -> DONE -> IDLE
// Verilog-2001, two-block separation (combinational + sequential)
//==============================================================================

module sm3_fsm (
    input  wire        clk,
    input  wire        rst_n,          // active-low async reset
    input  wire        msg_valid,
    input  wire        is_last,
    output wire        ready,          // registered, 1 during IDLE
    output wire        load_en,        // registered, single-cycle pulse at round_cnt==0
    output wire        calc_en,        // registered, level during CALC
    output wire        update_v_en,    // registered, single-cycle pulse in DONE
    output wire [5:0]  round_cnt,      // registered, 0-63 during CALC
    output wire        hash_valid      // registered, single-cycle pulse in DONE when is_last
);

    localparam ROUNDS = 64;
    localparam ROUND_CNT_WIDTH = 6;

    // FSM state encoding
    localparam [1:0] STATE_IDLE = 2'd0;
    localparam [1:0] STATE_CALC = 2'd1;
    localparam [1:0] STATE_DONE = 2'd2;

    // Internal registers
    reg [1:0] state_reg;
    reg [5:0] round_cnt_reg;
    reg       is_last_captured_reg;
    reg       ready_reg;
    reg       load_en_reg;
    reg       calc_en_reg;
    reg       update_v_en_reg;
    reg       hash_valid_reg;
    reg       hash_pending_reg;  // delayed: set in DONE, fires hash_valid in next cycle

    // Combinational next-state signals
    reg [1:0] state_next;
    reg [5:0] round_cnt_next;
    reg       is_last_captured_next;
    reg       ready_next;
    reg       load_en_next;
    reg       calc_en_next;
    reg       update_v_en_next;
    reg       hash_valid_next;
    reg       hash_pending_next;

    //==========================================================================
    // Combinational block — next-state logic with defaults
    //==========================================================================
    always @* begin
        // defaults
        state_next            = state_reg;
        round_cnt_next        = 6'd0;
        is_last_captured_next = is_last_captured_reg;
        ready_next            = 1'b0;
        load_en_next          = 1'b0;
        calc_en_next          = 1'b0;
        update_v_en_next      = 1'b0;
        hash_valid_next       = 1'b0;
        hash_pending_next     = hash_pending_reg;

        case (state_reg)
            STATE_IDLE: begin
                ready_next = 1'b1;
                if (hash_pending_reg) begin
                    hash_valid_next = 1'b1;
                    hash_pending_next = 1'b0;
                end
                if (msg_valid) begin
                    state_next = STATE_CALC;
                    is_last_captured_next = is_last;
                end
            end

            STATE_CALC: begin
                calc_en_next = 1'b1;
                if (calc_en_reg == 1'b0) begin
                    load_en_next = 1'b1;
                    round_cnt_next = 6'd0;
                end else begin
                    round_cnt_next = round_cnt_reg + 6'd1;
                end
                if (round_cnt_reg == 6'd63) begin
                    state_next = STATE_DONE;
                    calc_en_next = 1'b0;
                end
            end

            STATE_DONE: begin
                update_v_en_next = 1'b1;
                if (is_last_captured_reg) begin
                    hash_pending_next = 1'b1;
                end
                state_next = STATE_IDLE;
            end

            default: begin
                state_next = STATE_IDLE;
            end
        endcase
    end

    //==========================================================================
    // Sequential block — register update with async reset at end
    //==========================================================================
    always @(posedge clk) begin
        if (!rst_n) begin
            state_reg            <= STATE_IDLE;
            round_cnt_reg        <= 6'd0;
            is_last_captured_reg <= 1'b0;
            ready_reg            <= 1'b1;
            load_en_reg          <= 1'b0;
            calc_en_reg          <= 1'b0;
            update_v_en_reg      <= 1'b0;
            hash_valid_reg       <= 1'b0;
            hash_pending_reg     <= 1'b0;
        end else begin
            state_reg            <= state_next;
            round_cnt_reg        <= round_cnt_next;
            is_last_captured_reg <= is_last_captured_next;
            ready_reg            <= ready_next;
            load_en_reg          <= load_en_next;
            calc_en_reg          <= calc_en_next;
            update_v_en_reg      <= update_v_en_next;
            hash_valid_reg       <= hash_valid_next;
            hash_pending_reg     <= hash_pending_next;
        end
    end

    //==========================================================================
    // Output assignments — output wire = internal register
    //==========================================================================
    assign ready        = ready_reg;
    assign load_en      = load_en_reg;
    assign calc_en      = calc_en_reg;
    assign update_v_en  = update_v_en_reg;
    assign round_cnt    = round_cnt_reg;
    assign hash_valid   = hash_valid_reg;

endmodule
