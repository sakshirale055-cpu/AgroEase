CREATE TABLE IF NOT EXISTS payment (
    id SERIAL PRIMARY KEY,
    farmer_id INTEGER NOT NULL REFERENCES "user"(id),
    booking_id INTEGER UNIQUE REFERENCES booking(id),
    tractor_rental_id INTEGER UNIQUE REFERENCES tractor_rental(id),
    machinery_rental_id INTEGER UNIQUE REFERENCES machinery_rental(id),
    amount NUMERIC(10, 2) NOT NULL,
    payment_method VARCHAR(40) NOT NULL DEFAULT 'Demo',
    payment_status VARCHAR(30) NOT NULL DEFAULT 'Pending',
    transaction_id VARCHAR(80) UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_payment_farmer_id
ON payment (farmer_id);