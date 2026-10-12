from .database import db


class Booking(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	farmer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
	worker_id = db.Column(db.Integer, db.ForeignKey("worker.id"), nullable=False)
	booking_date = db.Column(db.Date, nullable=False)
	status = db.Column(db.String(30), default="Pending")

	farmer = db.relationship("User", backref="bookings")
	worker = db.relationship("Worker", backref="bookings")
