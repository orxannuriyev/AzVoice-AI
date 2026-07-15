-- ============================================================
-- Triggers
-- ============================================================

-- 1) automatic updated_at refresh
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'hotel_info','room_types','rooms','rate_plans','availability','guests',
        'reservations','services','campaigns','payments','call_logs',
        'knowledge_base','staff'
    ]
    LOOP
        EXECUTE format(
            'CREATE TRIGGER trg_%s_updated_at
             BEFORE UPDATE ON %I
             FOR EACH ROW EXECUTE FUNCTION set_updated_at()', t, t);
    END LOOP;
END $$;

-- ============================================================
-- 2) Availability synchronization
--
-- When a reservation is INSERTed booked_rooms increases,
-- when the status becomes cancelled it decreases.
-- Overbooking is blocked at the DB level with
-- CHECK (booked_rooms <= total_rooms) — the most reliable
-- guard rail for LLM tool calling.
-- ============================================================

CREATE OR REPLACE FUNCTION sync_availability()
RETURNS trigger AS $$
DECLARE
    d date;
BEGIN
    -- New reservation (not cancelled) → booked_rooms increases
    IF TG_OP = 'INSERT' AND NEW.status <> 'cancelled' THEN
        FOR d IN SELECT generate_series(NEW.check_in, NEW.check_out - 1, '1 day')::date LOOP
            UPDATE availability
               SET booked_rooms = booked_rooms + 1
             WHERE room_type_id = NEW.room_type_id AND date = d;
        END LOOP;

    ELSIF TG_OP = 'UPDATE' THEN
        -- active → cancelled : decrement
        IF OLD.status <> 'cancelled' AND NEW.status = 'cancelled' THEN
            FOR d IN SELECT generate_series(OLD.check_in, OLD.check_out - 1, '1 day')::date LOOP
                UPDATE availability
                   SET booked_rooms = GREATEST(booked_rooms - 1, 0)
                 WHERE room_type_id = OLD.room_type_id AND date = d;
            END LOOP;
        -- cancelled → active (restore) : increment
        ELSIF OLD.status = 'cancelled' AND NEW.status <> 'cancelled' THEN
            FOR d IN SELECT generate_series(NEW.check_in, NEW.check_out - 1, '1 day')::date LOOP
                UPDATE availability
                   SET booked_rooms = booked_rooms + 1
                 WHERE room_type_id = NEW.room_type_id AND date = d;
            END LOOP;
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_reservations_availability
AFTER INSERT OR UPDATE OF status ON reservations
FOR EACH ROW EXECUTE FUNCTION sync_availability();
