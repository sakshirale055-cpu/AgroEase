from datetime import datetime

from .database import db


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    farmer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("booking.id"), nullable=True, unique=True)
    tractor_rental_id = db.Column(db.Integer, db.ForeignKey("tractor_rental.id"), nullable=True, unique=True)
    machinery_rental_id = db.Column(db.Integer, db.ForeignKey("machinery_rental.id"), nullable=True, unique=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.String(40), nullable=False, default="Demo")
    payment_status = db.Column(db.String(30), nullable=False, default="Pending")
    transaction_id = db.Column(db.String(80), nullable=True, unique=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    farmer = db.relationship("User", backref="payments")
    tractor_rental = db.relationship(
        "TractorRental",
        backref=db.backref("payment_record", uselist=False),
    )
    machinery_rental = db.relationship(
        "MachineryRental",
        backref=db.backref("payment_record", uselist=False),
    )
    booking = db.relationship(
        "Booking",
        backref=db.backref("payment_record", uselist=False),
    )