-- ============================================================
-- Indexes
-- ============================================================

-- FK columns (btree)
CREATE INDEX idx_rooms_room_type        ON rooms(room_type_id);
CREATE INDEX idx_rate_plans_room_type   ON rate_plans(room_type_id);
CREATE INDEX idx_reservations_guest     ON reservations(guest_id);
CREATE INDEX idx_reservations_room_type ON reservations(room_type_id);
CREATE INDEX idx_reservations_room      ON reservations(room_id);
CREATE INDEX idx_payments_reservation   ON payments(reservation_id);

-- Composite indexes
CREATE INDEX idx_availability_type_date ON availability(room_type_id, date);
CREATE INDEX idx_reservations_dates     ON reservations(check_in, check_out);
CREATE INDEX idx_call_logs_created      ON call_logs(created_at);

-- Call center: quickly find the caller by phone number
-- (guests.phone is UNIQUE, so an index is created automatically)

-- RAG: HNSW for semantic search (cosine)
CREATE INDEX idx_kb_embedding ON knowledge_base
    USING hnsw (embedding vector_cosine_ops);
