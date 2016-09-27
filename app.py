# -*- coding: utf-8 -*-

import json
import logging
from datetime import timedelta
from bson import ObjectId

from flask import Flask, request, jsonify
from flask_jwt import JWT, jwt_required

from py import user
from py import jwt_auth
from py import subject
from py import link
from py.idmexception import IDMException
from py.jsondocument import mongoserver

# read settings
try:
	import settings
except Exception:
	logging.warn('No `settings.py` present, using `defaults.py`')
	import defaults as settings


# JSON encoder that handles BSON
class BSONEncoder(json.JSONEncoder):
	def default(self, o):
		if isinstance(o, ObjectId):
			return str(o)
		return json.JSONEncoder.default(self, o)


# app setup
app = Flask(__name__)
app.config['SECRET_KEY'] = settings.jwt['secret']
app.config['JWT_EXPIRATION_DELTA'] = timedelta(seconds=int(settings.jwt['expiration_seconds']))
app.json_encoder = BSONEncoder
jwt = JWT(app, jwt_auth.authenticate, jwt_auth.identity)

mng_bkt = settings.mongo_server['bucket']
mng_srv = mongoserver.MongoServer(
	host=settings.mongo_server['host'],
	port=settings.mongo_server['port'],
	database=settings.mongo_server['db'],
	bucket=mng_bkt,
	user=settings.mongo_server['user'],
	pw=settings.mongo_server['password'])

def _err(message, status=400, headers=None):
	body = jsonify({'error': {'status': status, 'message': message}})
	return (body, status, headers) if headers is not None else (body, status)

def _exc(exception):
	if isinstance(exception, IDMException):
		return _err(str(exception), status=exception.status_code)
	return _err(str(exception))

@app.errorhandler(404)
def _not_found(error):
	return _err(error.name, status=error.code)

@jwt.jwt_error_handler
def _jwt_err(error):
	return _err(error.error, status=error.status_code, headers=error.headers)

def _subject_with_sssid(sssid):
	rslt = subject.Subject.find_sssid_on(sssid, mng_srv, mng_bkt)
	if len(rslt) > 0:
		pat = rslt[0]
		if len(rslt) > 1:
			logging.warn("there are {} subjects with SSSID {}".format(len(rslt), sssid))
		return pat
	return None


# routes
@app.route('/')
def index():
	""" The service root.
	"""
	return jsonify({'status': 'ready'})


# MARK: - Subjects

@app.route('/subject', methods=['GET', 'POST'])
@jwt_required()
def subject_ep():
	
	# create (fails if SSSID already exists)
	if 'POST' == request.method:
		js = request.json
		#return jsonify({'you': 'posted', 'data': js})
		if not js or not 'sssid' in js:
			return _err('must at least provide `sssid`')
		
		subj = _subject_with_sssid(js['sssid'])
		if subj is not None:
			return _err('this SSSID is already taken', 409)
		
		try:
			subject.Subject.validate_json(js)
			subj = subject.Subject(js['sssid'], js)
			del subj._id   # auto-creates UUID; we rely on Mongo
			subj.store_to(mng_srv, mng_bkt)
		except Exception as e:
			return _exc(e)
		return jsonify({'data': subj.for_api()}), 201
	
	# list
	rslt = subject.Subject.find_on({'type': 'subject'}, mng_srv, mng_bkt)
	return jsonify({'data': [p.for_api() for p in rslt]})

@app.route('/subject/<sssid>', methods=['GET', 'PUT'])
@jwt_required()
def subject_sssid(sssid):
	subj = _subject_with_sssid(sssid)
	if subj is None:
		return _err('Not Found', status=404)
	
	# update
	if 'PUT' == request.method:
		try:
			subj.safe_update_and_store_to(request.json, mng_srv, mng_bkt)
		except Exception as e:
			return _exc(e)
		return '', 204
	
	# get
	return jsonify({'data': subj.for_api()})


# MARK: - Links

@app.route('/link/<jti>/jwt')
def link_jti_jwt(jti, methods=['GET']):
	lnk = link.Link.find_jti_on(jti, mng_srv, mng_bkt)
	if lnk is None:
		return _err('Not Found', status=404)
	try:
		
		# update link
		if 'PUT' == request.method:
			return 'Not implemented', 500
		
		# get JWT
		return lnk.jwt(mng_srv, bucket=mng_bkt)
	
	except Exception as e:
		return _exc(e)

@app.route('/link/<jti>', methods=['GET', 'PUT'])
@jwt_required()
def link_jti(jti):
	lnk = link.Link.find_jti_on(jti, mng_srv, mng_bkt)
	if lnk is None:
		return _err('Not Found', status=404)
	
	# update link
	if 'PUT' == request.method:
		try:
			lnk.safe_update_and_store_to(request.json, mng_srv, mng_bkt)
		except Exception as e:
			return _exc(e)
		return 'Not implemented', 500
	
	# get
	return jsonify({'data': lnk.for_api()})

@app.route('/subject/<sssid>/links', methods=['GET', 'POST'])
@jwt_required()
def subject_sssid_link(sssid):
	subj = _subject_with_sssid(sssid)
	if subj is None:
		return _err('Not Found', status=404)

	# create a new link
	if 'POST' == request.method:
		try:
			lnk = link.Link(None, json={
				'sub': sssid,
				'iss': settings.jwt['iss'],
				'aud': settings.jwt['aud'],
				'secret': settings.jwt['secret'],
				'algorithm': settings.jwt['algorithm']})
			del lnk._id   # auto-creates UUID; we rely on Mongo
			lnk.store_to(mng_srv, mng_bkt)
		except Exception as e:
			return _exc(e)
		return jsonify({'data': lnk.for_api()}), 201
	
	# return all links for this SSSID
	return 'Not implemented', 500


# start the app
if '__main__' == __name__:
	logging.basicConfig(level=logging.DEBUG)
	app.run(debug=True, port=9096)
