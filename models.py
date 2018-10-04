import time

from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey
import sqlalchemy.types as types
from sqlalchemy.orm import relationship
from sqlalchemy.sql.expression import func
from sqlalchemy import or_, and_, desc
from marshmallow import Schema, fields

from database import Base

class FoilSchema(Schema):
    date = fields.Integer()
    batch = fields.Integer()
    private_key = fields.String()
    amount = fields.Integer()
    funding_txid = fields.String()
    funding_date = fields.Integer()
    expiry = fields.Integer()

class Foil(Base):
    __tablename__ = 'foils'
    id = Column(Integer, primary_key=True)
    date = Column(Integer, nullable=False)
    batch = Column(Integer, nullable=False)
    private_key = Column(String, nullable=False, unique=True)
    amount = Column(Integer, nullable=False)
    funding_txid = Column(String, nullable=True, unique=True)
    funding_date = Column(Integer, nullable=True)
    expiry = Column(Integer, nullable=True)

    def __init__(self, date, batch, private_key, amount, funding_txid, funding_date, expiry):
        self.date = date
        self.batch = batch
        self.private_key = private_key
        self.amount = amount
        self.funding_txid = funding_txid
        self.funding_date = funding_date
        self.expiry = expiry

    @classmethod
    def from_txid(cls, session, funding_txid):
        return session.query(cls).filter(cls.funding_txid == funding_txid).first()

    @classmethod
    def all(cls, session):
        return session.query(cls).all()

    @classmethod
    def get_batch(cls, session, batch):
        return session.query(cls).filter(cls.batch == batch).all()

    @classmethod
    def next_batch_id(cls, session):
        batch = 1
        while True:
            foils = cls.get_batch(session, batch)
            if not foils:
                break
            batch += 1
        return batch

    @classmethod
    def count(cls, session):
        return session.query(cls).count()

    def __repr__(self):
        return '<Foil %r>' % (self.funding_txid)

    def to_json(self):
        foil_schema = FoilSchema()
        return foil_schema.dump(self).data
