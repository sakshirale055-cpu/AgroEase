ALTER TABLE review
ADD COLUMN IF NOT EXISTS rental_id INTEGER
REFERENCES machinery_rental(id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_review_rental_id
ON review (rental_id)
WHERE rental_id IS NOT NULL;