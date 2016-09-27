# -*- coding: utf-8 -*-

from datetime import datetime
from flask_jwt import current_identity

from .jsondocument import jsondocument
from .idmexception import IDMException


class Subject(jsondocument.JSONDocument):
	
	def __init__(self, sssid, json=None):
		self.sssid = sssid
		super().__init__(None, 'subject', json)
	
	
	# MARK: - Validation
	
	@classmethod
	def validate_json(cls, js):
		if js is None:
			raise Exception("No JSON provided")
		for key in ['sssid', 'name', 'bday']:
			if key not in js:
				raise Exception("JSON is missing the `{}` element".format(key))
			if not js[key]:
				raise Exception("The `{}` element is empty".format(key))
		try:
			datetime.strptime(js['bday'], '%Y-%m-%d')
		except Exception as e:
			raise Exception("The birth date \"{}\" is not properly formatted".format(js['bday']))
	
	
	# MARK: - CRUD
	
	def safe_update_and_store_to(self, js, server, bucket):
		""" Takes data sent via the web and updates the receiver. Will check
		if self.status changes and use it as audit action.
		"""
		self.__class__.validate_json(js)
		if js['sssid'] != self.sssid:
			raise IDMException('SSSID cannot be changed', 409)
		if 'type' in js:
			del js['type']
		
		statuschange = None
		if 'status' in js and js['status'] != self.status:
			statuschange = '{} -> {}'.format(self.status, js['status'])
		
		self.update_with(js)
		self.store_to(server, bucket, statuschange)
	
	def store_to(self, server, bucket=None, action=None):
		""" Override to simultaneously store an "audit" document when storing
		subject documents.
		"""
		now = int(datetime.timestamp(datetime.utcnow()))
		actor = current_identity.id if current_identity is not None else None
		doc = jsondocument.JSONDocument(None, 'audit', {'actor': actor, 'epoch': now})
		if self.created is None:
			self.created = now
			doc.update_with({'action': 'create'})
		else:
			self.changed = now
			doc.update_with({'action': action or 'update'})
		super().store_to(server, bucket)
		doc.update_with({'document': self.id})
		doc.store_to(server, bucket)
	
	def for_api(self):
		return super().for_api(omit=['_id', 'id'])
	
	
	# MARK: - Search
	
	@classmethod
	def find_sssid_on(cls, sssid, server, bucket=None):
		if not sssid:
			return None
		return cls.find_on({'type': 'subject', 'sssid': sssid}, server, bucket)
