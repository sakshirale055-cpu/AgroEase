from .database import db


class User(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String(100), nullable=False)
	email = db.Column(db.String(120), unique=True, nullable=False)
	password = db.Column(db.String(200), nullable=False)
	role = db.Column(db.String(30), nullable=False)
	roles = db.Column(db.String(200), nullable=False, default="")
	phone = db.Column(db.String(20), nullable=True)
	location = db.Column(db.String(100), nullable=True)
	online_payment_methods = db.Column(db.String(100), nullable=False, default="")
	bank_name = db.Column(db.String(100), nullable=True)
	bank_account_number = db.Column(db.String(34), nullable=True)
	demo_cardholder_name = db.Column(db.String(100), nullable=True)
	demo_card_number = db.Column(db.String(6), nullable=True)
	demo_card_expiry = db.Column(db.String(7), nullable=True)
	qr_code_filename = db.Column(db.String(255), nullable=True)
	worker_profile = db.relationship("Worker", back_populates="user", uselist=False)

	@property
	def available_online_payment_methods(self):
		supported = {"net_banking", "debit_card", "qr_code"}
		return [
			method for method in (self.online_payment_methods or "").split(",")
			if method in supported
		]

	@property
	def formatted_online_payment_methods(self):
		labels = {
			"net_banking": "Net Banking",
			"debit_card": "Debit Card",
			"qr_code": "QR Code",
		}
		return [labels[method] for method in self.available_online_payment_methods]

	@property
	def account_roles(self):
		roles = [role.strip() for role in (self.roles or "").split(",") if role.strip()]
		if self.role and self.role not in roles:
			roles.insert(0, self.role)
		return list(dict.fromkeys(roles))
