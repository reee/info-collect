from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    internal_id = db.Column(db.String(10), unique=True)
    name = db.Column(db.String(100), nullable=False)
    gender = db.Column(db.String(10), nullable=False)
    class_name = db.Column(db.String(100), nullable=False)
    noon_leaving = db.Column(db.Boolean, nullable=False)
    night_leaving = db.Column(db.Boolean, nullable=False)
    day_student = db.Column(db.Boolean, nullable=False)
    boarding_student = db.Column(db.Boolean, nullable=False)
    remarks = db.Column(db.String(255))
    photo_filename = db.Column(db.String(255))

    def __repr__(self):
        return '<Student %r>' % self.name

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)