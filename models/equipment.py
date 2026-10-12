from .database import db


class Tractor(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
	name = db.Column(db.String(100), nullable=False)
	brand = db.Column(db.String(100), nullable=False)
	rent_per_day = db.Column(db.Float, nullable=False)
	location = db.Column(db.String(100), nullable=False)
	available = db.Column(db.Boolean, default=True)
	image_filename = db.Column(db.String(255), nullable=True)

	owner = db.relationship("User", backref="tractors")


class TractorRental(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	farmer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
	tractor_id = db.Column(db.Integer, db.ForeignKey("tractor.id"), nullable=False)
	rental_date = db.Column(db.Date, nullable=False)
	start_date = db.Column(db.Date, nullable=True)
	end_date = db.Column(db.Date, nullable=True)
	status = db.Column(db.String(30), default="Pending")

	farmer = db.relationship("User", backref="tractor_rentals")
	tractor = db.relationship("Tractor", backref="rentals")


class Machinery(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
	name = db.Column(db.String(100), nullable=False)
	type = db.Column(db.String(100), nullable=False)
	rent_per_day = db.Column(db.Float, nullable=False)
	location = db.Column(db.String(100), nullable=False)
	available = db.Column(db.Boolean, default=True)
	image_filename = db.Column(db.String(255), nullable=True)

	owner = db.relationship("User", backref="machinery")


class MachineryRental(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	farmer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
	machinery_id = db.Column(db.Integer, db.ForeignKey("machinery.id"), nullable=False)
	rental_date = db.Column(db.Date, nullable=False)
	start_date = db.Column(db.Date, nullable=True)
	end_date = db.Column(db.Date, nullable=True)
	status = db.Column(db.String(30), default="Pending")

	farmer = db.relationship("User", backref="machinery_rentals")
	machinery = db.relationship("Machinery", backref="rentals")
