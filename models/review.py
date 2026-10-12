from .database import db


class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    farmer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    machinery_id = db.Column(db.Integer, db.ForeignKey("machinery.id"), nullable=True)
    rental_id = db.Column(
        db.Integer,
        db.ForeignKey("machinery_rental.id"),
        unique=True,
        nullable=True,
    )
    worker_id = db.Column(db.Integer, db.ForeignKey("worker.id"), nullable=True)
    booking_id = db.Column(
        db.Integer,
        db.ForeignKey("booking.id"),
        unique=True,
        nullable=True,
    )
    tractor_id = db.Column(db.Integer, db.ForeignKey("tractor.id"), nullable=True)
    tractor_rental_id = db.Column(
        db.Integer,
        db.ForeignKey("tractor_rental.id"),
        unique=True,
        nullable=True,
    )
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=False)

    farmer = db.relationship("User", backref="reviews")
    machinery = db.relationship("Machinery", backref="reviews")
    rental = db.relationship("MachineryRental", backref="review")
    worker = db.relationship("Worker", backref="reviews")
    booking = db.relationship("Booking", backref="review")
    tractor = db.relationship("Tractor", backref="reviews")
    tractor_rental = db.relationship("TractorRental", backref="review")