-- ============================================================
-- İndekslər
-- ============================================================

-- FK sahələri (btree)
CREATE INDEX idx_rooms_room_type        ON rooms(room_type_id);
CREATE INDEX idx_rate_plans_room_type   ON rate_plans(room_type_id);
CREATE INDEX idx_reservations_guest     ON reservations(guest_id);
CREATE INDEX idx_reservations_room_type ON reservations(room_type_id);
CREATE INDEX idx_reservations_room      ON reservations(room_id);
CREATE INDEX idx_payments_reservation   ON payments(reservation_id);

-- Composite indekslər
CREATE INDEX idx_availability_type_date ON availability(room_type_id, date);
CREATE INDEX idx_reservations_dates     ON reservations(check_in, check_out);
CREATE INDEX idx_call_logs_created      ON call_logs(created_at);

-- Call center: zəngedəni telefon nömrəsi ilə tez tapmaq
-- (guests.phone UNIQUE olduğu üçün index avtomatik yaranır)

-- RAG: semantik axtarış üçün HNSW (cosine)
CREATE INDEX idx_kb_embedding ON knowledge_base
    USING hnsw (embedding vector_cosine_ops);
