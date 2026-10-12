from .database import db


class Worker(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=True)
	name = db.Column(db.String(100), nullable=False)
	phone = db.Column(db.String(20), nullable=False)
	skill = db.Column(db.String(100), nullable=False)
	location = db.Column(db.String(100), nullable=False)
	rate_per_day = db.Column(db.Numeric(10, 2), nullable=True)
	available = db.Column(db.Boolean, default=True)
	image_filename = db.Column(db.String(255), nullable=True)
	user = db.relationship("User", back_populates="worker_profile")
