//----------------------------------------------------------------------
// Module: sm3_fsm
// Description: SM3 hash FSM controller
//              Controls SM3 compression function state machine
//----------------------------------------------------------------------
module sm3_fsm (
    input  wire        clk,
    input  wire        rst,
    input  wire        msg_valid,
    input  wire        is_last,
    output wire        ready,
    output wire        load_en,
    output wire        calc_en,
    output wire        update_v_en,
    output wire [5:0]  round_cnt,
    output wire        hash_valid
);

    //------------------------------------------------------------------
    // State definitions
    //------------------------------------------------------------------
    localparam IDLE = 2'b00;
    localparam CALC = 2'b01;
    localparam DONE = 2'b10;

    //------------------------------------------------------------------
    // Internal state registers
    //------------------------------------------------------------------
    reg [1:0]  state_reg      = IDLE;
    reg [1:0]  next_state;

    reg [5:0]  round_cnt_reg  = 6'd0;
    reg [5:0]  next_round_cnt;

    reg        ready_reg     = 1'b0;
    reg        load_en_reg   = 1'b0;
    reg        calc_en_reg   = 1'b0;
    reg        update_v_en_reg = 1'b0;
    reg        hash_valid_reg = 1'b0;

    //------------------------------------------------------------------
    // Combinational logic - state transition and output decoding
    //------------------------------------------------------------------
    always @* begin
        // Default assignments
        next_state       = state_reg;
        next_round_cnt   = round_cnt_reg;
        ready_reg       = 1'b0;
        load_en_reg     = 1'b0;
        calc_en_reg     = 1'b0;
        update_v_en_reg = 1'b0;
        hash_valid_reg  = 1'b0;

        // State machine logic
        case (state_reg)
            IDLE: begin
                ready_reg = 1'b1;
                if (msg_valid == 1'b1) begin
                    next_state = CALC;
                    load_en_reg = 1'b1;
                end
            end

            CALC: begin
                calc_en_reg = 1'b1;
                next_round_cnt = round_cnt_reg + 1'b1;

                if (round_cnt_reg == 6'd63) begin
                    next_state = DONE;
                    next_round_cnt = 6'd0;
                end
            end

            DONE: begin
                update_v_en_reg = 1'b1;
                hash_valid_reg = is_last;
                next_state = IDLE;
            end

            default: begin
                next_state = IDLE;
            end
        endcase
    end

    //------------------------------------------------------------------
    // Sequential logic - state and register updates
    //------------------------------------------------------------------
    always @(posedge clk) begin
        if (rst == 1'b1) begin
            // Reset to IDLE state
            state_reg       <= IDLE;
            round_cnt_reg   <= 6'd0;
            ready_reg       <= 1'b1;
            load_en_reg     <= 1'b0;
            calc_en_reg     <= 1'b0;
            update_v_en_reg <= 1'b0;
            hash_valid_reg  <= 1'b0;
        end else begin
            state_reg       <= next_state;
            round_cnt_reg   <= next_round_cnt;
            ready_reg       <= ready_reg;
            load_en_reg     <= load_en_reg;
            calc_en_reg     <= calc_en_reg;

            // When transitioning from DONE to IDLE, clear update_v_en and hash_valid
            if (state_reg == DONE && next_state == IDLE) begin
                update_v_en_reg <= 1'b0;
                hash_valid_reg  <= 1'b0;
            end else begin
                update_v_en_reg <= update_v_en_reg;
                hash_valid_reg  <= hash_valid_reg;
            end
        end
    end

    //------------------------------------------------------------------
    // Output assignments
    //------------------------------------------------------------------
    assign ready       = ready_reg;
    assign load_en     = load_en_reg;
    assign calc_en     = calc_en_reg;
    assign update_v_en = update_v_en_reg;
    assign round_cnt   = round_cnt_reg;
    assign hash_valid  = hash_valid_reg;

endmodule
