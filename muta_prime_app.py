from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import pymysql
import os
pymysql.install_as_MySQLdb()

app = Flask(__name__)
CORS(app)

# ✅ Reads from Railway environment variable
db_url = os.environ.get('DATABASE_URL', '')
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'mutaprime_secret_key'

db = SQLAlchemy(app)


# ─────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────

class User(db.Model):
    __tablename__ = 'users'
    id           = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name         = db.Column(db.String(255), nullable=False)
    email        = db.Column(db.String(255), unique=True, nullable=False)
    password     = db.Column(db.String(255), nullable=False)
    organization = db.Column(db.String(255), default='')
    role         = db.Column(db.String(100), default='Research Scientist')
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

class ActiveSession(db.Model):
    __tablename__ = 'active_sessions'
    id       = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email    = db.Column(db.String(255), nullable=False)
    login_at = db.Column(db.DateTime, default=datetime.utcnow)

class AnalysisJob(db.Model):
    __tablename__ = 'analysis_jobs'
    id              = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name            = db.Column(db.String(255), nullable=False)
    sequence        = db.Column(db.Text, nullable=False)
    sequence_length = db.Column(db.Integer, nullable=False)
    primer_len_min  = db.Column(db.Integer, default=18)
    primer_len_max  = db.Column(db.Integer, default=25)
    gc_min          = db.Column(db.Float, default=40.0)
    gc_max          = db.Column(db.Float, default=60.0)
    tm_min          = db.Column(db.Float, default=55.0)
    tm_max          = db.Column(db.Float, default=65.0)
    max_self_comp   = db.Column(db.Float, default=8.0)
    max_three_comp  = db.Column(db.Float, default=3.0)
    status          = db.Column(db.String(20), default='pending')
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

class Primer(db.Model):
    __tablename__ = 'primers'
    id               = db.Column(db.Integer, primary_key=True, autoincrement=True)
    job_id           = db.Column(db.Integer, db.ForeignKey('analysis_jobs.id'), nullable=False)
    user_id          = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    sequence         = db.Column(db.String(100), nullable=False)
    length           = db.Column(db.Integer, nullable=False)
    gc_percent       = db.Column(db.Float, nullable=False)
    tm               = db.Column(db.Float, nullable=False)
    self_comp        = db.Column(db.Float, default=0.0)
    three_comp       = db.Column(db.Float, default=0.0)
    robustness_score = db.Column(db.Integer, default=0)
    position         = db.Column(db.Integer, default=0)
    strand           = db.Column(db.String(10), default='forward')
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)

class MutationSimulation(db.Model):
    __tablename__ = 'mutation_simulations'
    id                  = db.Column(db.Integer, primary_key=True, autoincrement=True)
    job_id              = db.Column(db.Integer, db.ForeignKey('analysis_jobs.id'), nullable=False)
    user_id             = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    mutation_type       = db.Column(db.String(50), nullable=False)
    frequency           = db.Column(db.Float, nullable=False)
    num_simulations     = db.Column(db.Integer, default=1000)
    binding_conserved   = db.Column(db.Float, default=0.0)
    binding_reduced     = db.Column(db.Float, default=0.0)
    binding_lost        = db.Column(db.Float, default=0.0)
    population_coverage = db.Column(db.Float, default=0.0)
    ai_insight          = db.Column(db.Text, nullable=True)
    created_at          = db.Column(db.DateTime, default=datetime.utcnow)

class MutationDetail(db.Model):
    __tablename__ = 'mutation_details'
    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    simulation_id = db.Column(db.Integer, db.ForeignKey('mutation_simulations.id'), nullable=False)
    position      = db.Column(db.Integer, nullable=False)
    original_base = db.Column(db.String(5), nullable=False)
    mutated_base  = db.Column(db.String(5), nullable=False)
    mutation_type = db.Column(db.String(50), nullable=False)
    effect        = db.Column(db.String(100), nullable=False)
    impact        = db.Column(db.String(20), default='Low')
    score         = db.Column(db.Integer, default=0)

class DimerResult(db.Model):
    __tablename__ = 'dimer_results'
    id              = db.Column(db.Integer, primary_key=True, autoincrement=True)
    job_id          = db.Column(db.Integer, db.ForeignKey('analysis_jobs.id'), nullable=False)
    primer_id       = db.Column(db.Integer, db.ForeignKey('primers.id'), nullable=False)
    delta_g         = db.Column(db.Float, nullable=False)
    complementarity = db.Column(db.Integer, default=0)
    stability_score = db.Column(db.Integer, default=0)
    risk_level      = db.Column(db.String(10), nullable=False)
    ai_analysis     = db.Column(db.Text, nullable=True)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────

@app.route('/signup', methods=['POST'])
def signup():
    try:
        data     = request.get_json()
        required = ['name', 'email', 'password', 'confirm_password']
        if not data or not all(k in data for k in required):
            return jsonify({'error': 'Missing required fields'}), 400
        if data['password'] != data['confirm_password']:
            return jsonify({'error': 'Passwords do not match'}), 400
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'error': 'Email already registered'}), 409
        user = User(
            name=data['name'], email=data['email'],
            password=generate_password_hash(data['password']),
            organization=data.get('organization', ''),
            role=data.get('role', 'Research Scientist')
        )
        db.session.add(user)
        db.session.commit()
        return jsonify({'message': 'Account created successfully'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        if not data or 'email' not in data or 'password' not in data:
            return jsonify({'error': 'Email and password required'}), 400
        user = User.query.filter_by(email=data['email']).first()
        if not user or not check_password_hash(user.password, data['password']):
            return jsonify({'error': 'Invalid credentials'}), 401
        session = ActiveSession(email=user.email)
        db.session.add(session)
        db.session.commit()
        return jsonify({'message': 'Login successful', 'user': {
            'id': user.id, 'name': user.name, 'email': user.email,
            'organization': user.organization, 'role': user.role
        }}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/get_current_user', methods=['GET'])
def get_current_user():
    try:
        last = ActiveSession.query.order_by(ActiveSession.id.desc()).first()
        if not last:
            return jsonify({'error': 'No active session'}), 404
        user = User.query.filter_by(email=last.email).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        return jsonify({
            'id': user.id, 'name': user.name, 'email': user.email,
            'organization': user.organization, 'role': user.role
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/logout', methods=['POST'])
def logout():
    try:
        data  = request.get_json()
        email = data.get('email') if data else None
        if not email:
            return jsonify({'error': 'Email required'}), 400
        ActiveSession.query.filter_by(email=email).delete()
        db.session.commit()
        return jsonify({'message': 'Logged out successfully'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────
# PROFILE
# ─────────────────────────────────────────

@app.route('/profile/<int:user_id>', methods=['GET'])
def get_profile(user_id):
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        total_jobs    = AnalysisJob.query.filter_by(user_id=user_id).count()
        total_primers = Primer.query.filter_by(user_id=user_id).count()
        return jsonify({
            'id': user.id, 'name': user.name, 'email': user.email,
            'organization': user.organization, 'role': user.role,
            'created_at': user.created_at.strftime('%d %b %Y'),
            'total_analyses': total_jobs,
            'total_primers': total_primers
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/profile/<int:user_id>', methods=['PUT'])
def update_profile(user_id):
    try:
        data = request.get_json()
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        user.name         = data.get('name',         user.name)
        user.organization = data.get('organization', user.organization)
        user.role         = data.get('role',         user.role)
        db.session.commit()
        return jsonify({'message': 'Profile updated'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────
# ANALYSIS JOBS
# ─────────────────────────────────────────

@app.route('/jobs/<int:user_id>', methods=['GET'])
def get_jobs(user_id):
    try:
        jobs = AnalysisJob.query.filter_by(user_id=user_id)\
            .order_by(AnalysisJob.created_at.desc()).all()
        return jsonify([{
            'id': j.id, 'name': j.name,
            'sequence_length': j.sequence_length,
            'status': j.status,
            'primer_count': Primer.query.filter_by(job_id=j.id).count(),
            'created_at': j.created_at.strftime('%d %b %Y %H:%M')
        } for j in jobs]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/jobs', methods=['POST'])
def create_job():
    try:
        data     = request.get_json()
        required = ['user_id', 'sequence']
        if not data or not all(k in data for k in required):
            return jsonify({'error': 'Missing required fields'}), 400
        sequence = data['sequence'].strip().upper()
        if len(sequence) < 20:
            return jsonify({'error': 'Sequence too short (min 20 bp)'}), 400
        job = AnalysisJob(
            user_id         = data['user_id'],
            name            = data.get('name', f'Analysis {datetime.utcnow().strftime("%d%b%H%M")}'),
            sequence        = sequence,
            sequence_length = len(sequence),
            primer_len_min  = data.get('primer_len_min', 18),
            primer_len_max  = data.get('primer_len_max', 25),
            gc_min          = data.get('gc_min', 40.0),
            gc_max          = data.get('gc_max', 60.0),
            tm_min          = data.get('tm_min', 55.0),
            tm_max          = data.get('tm_max', 65.0),
            max_self_comp   = data.get('max_self_comp', 8.0),
            max_three_comp  = data.get('max_three_comp', 3.0),
            status          = 'done'
        )
        db.session.add(job)
        db.session.flush()
        primers = _generate_primers(job)
        for p in primers:
            db.session.add(p)
        db.session.commit()
        return jsonify({
            'message': 'Job created',
            'job_id': job.id,
            'primer_count': len(primers)
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/jobs/<int:job_id>', methods=['GET'])
def get_job(job_id):
    try:
        job = AnalysisJob.query.get(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        return jsonify({
            'id': job.id, 'name': job.name,
            'sequence': job.sequence,
            'sequence_length': job.sequence_length,
            'params': {
                'primer_len_min': job.primer_len_min,
                'primer_len_max': job.primer_len_max,
                'gc_min': job.gc_min, 'gc_max': job.gc_max,
                'tm_min': job.tm_min, 'tm_max': job.tm_max,
                'max_self_comp': job.max_self_comp,
                'max_three_comp': job.max_three_comp,
            },
            'status': job.status,
            'created_at': job.created_at.strftime('%d %b %Y %H:%M')
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/jobs/<int:job_id>', methods=['DELETE'])
def delete_job(job_id):
    try:
        job = AnalysisJob.query.get(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        Primer.query.filter_by(job_id=job_id).delete()
        MutationSimulation.query.filter_by(job_id=job_id).delete()
        DimerResult.query.filter_by(job_id=job_id).delete()
        db.session.delete(job)
        db.session.commit()
        return jsonify({'message': 'Job deleted'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────
# PRIMERS
# ─────────────────────────────────────────

@app.route('/primers/<int:job_id>', methods=['GET'])
def get_primers(job_id):
    try:
        limit   = int(request.args.get('limit', 50))
        primers = Primer.query.filter_by(job_id=job_id)\
            .order_by(Primer.robustness_score.desc()).limit(limit).all()
        return jsonify([{
            'id': p.id, 'sequence': p.sequence, 'length': p.length,
            'gc_percent': p.gc_percent, 'tm': p.tm,
            'self_comp': p.self_comp, 'three_comp': p.three_comp,
            'robustness_score': p.robustness_score,
            'position': p.position, 'strand': p.strand
        } for p in primers]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/primers/top5/<int:job_id>', methods=['GET'])
def get_top5_primers(job_id):
    try:
        primers = Primer.query.filter_by(job_id=job_id)\
            .order_by(Primer.robustness_score.desc()).limit(5).all()
        return jsonify([{
            'id': p.id, 'sequence': p.sequence,
            'gc_percent': p.gc_percent, 'tm': p.tm,
            'robustness_score': p.robustness_score
        } for p in primers]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/primers/summary/<int:job_id>', methods=['GET'])
def get_primer_summary(job_id):
    try:
        primers = Primer.query.filter_by(job_id=job_id).all()
        if not primers:
            return jsonify({'error': 'No primers found'}), 404
        scores       = [p.robustness_score for p in primers]
        avg_score    = round(sum(scores) / len(scores), 1)
        hairpins     = sum(1 for p in primers if p.self_comp > 6)
        self_dimers  = sum(1 for p in primers if p.self_comp > 5)
        cross_dimers = sum(1 for p in primers if p.three_comp > 2)
        avg_dg       = round(sum(p.self_comp * -0.8 for p in primers) / len(primers), 1)
        return jsonify({
            'total': len(primers),
            'avg_robustness': avg_score,
            'high_risk': sum(1 for p in primers if p.self_comp > 8 or p.three_comp > 3),
            'hairpins': hairpins,
            'self_dimers': self_dimers,
            'cross_dimers': cross_dimers,
            'avg_delta_g': avg_dg,
            'mutation_tolerance': min(99, avg_score + 5)
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────
# ROBUSTNESS
# ─────────────────────────────────────────

@app.route('/robustness/<int:job_id>', methods=['GET'])
def get_robustness(job_id):
    try:
        primers = Primer.query.filter_by(job_id=job_id).all()
        if not primers:
            return jsonify({'error': 'No primers found'}), 404
        scores = [p.robustness_score for p in primers]
        high   = [s for s in scores if s >= 90]
        medium = [s for s in scores if 70 <= s < 90]
        low    = [s for s in scores if s < 70]
        total  = len(scores)
        buckets = [0] * 5
        for s in scores:
            idx = min(4, max(0, (s - 50) // 10))
            buckets[idx] += 1
        return jsonify({
            'total': total,
            'robust_count': len(high),
            'avg_score': round(sum(scores) / total, 1),
            'high_risk_count': len(low),
            'distribution': {
                'high':   {'count': len(high),   'percent': round(len(high)   / total * 100, 1)},
                'medium': {'count': len(medium), 'percent': round(len(medium) / total * 100, 1)},
                'low':    {'count': len(low),    'percent': round(len(low)    / total * 100, 1)},
            },
            'histogram': [
                {'range': '50-60',  'count': buckets[0]},
                {'range': '60-70',  'count': buckets[1]},
                {'range': '70-80',  'count': buckets[2]},
                {'range': '80-90',  'count': buckets[3]},
                {'range': '90-100', 'count': buckets[4]},
            ]
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────
# MUTATION SIMULATION
# ─────────────────────────────────────────

@app.route('/mutations/<int:job_id>', methods=['GET'])
def get_mutations(job_id):
    try:
        sims   = MutationSimulation.query.filter_by(job_id=job_id)\
            .order_by(MutationSimulation.created_at.desc()).all()
        result = []
        for s in sims:
            details = MutationDetail.query.filter_by(simulation_id=s.id).all()
            result.append({
                'id': s.id,
                'mutation_type': s.mutation_type,
                'frequency': s.frequency,
                'num_simulations': s.num_simulations,
                'binding_conserved': s.binding_conserved,
                'binding_reduced': s.binding_reduced,
                'binding_lost': s.binding_lost,
                'population_coverage': s.population_coverage,
                'ai_insight': s.ai_insight,
                'created_at': s.created_at.strftime('%d %b %Y %H:%M'),
                'details': [{
                    'position': d.position,
                    'original_base': d.original_base,
                    'mutated_base': d.mutated_base,
                    'mutation_type': d.mutation_type,
                    'effect': d.effect,
                    'impact': d.impact,
                    'score': d.score
                } for d in details]
            })
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/mutations', methods=['POST'])
def save_mutation_simulation():
    try:
        data     = request.get_json()
        required = ['job_id', 'user_id', 'mutation_type', 'frequency']
        if not data or not all(k in data for k in required):
            return jsonify({'error': 'Missing required fields'}), 400
        sim = MutationSimulation(
            job_id              = data['job_id'],
            user_id             = data['user_id'],
            mutation_type       = data['mutation_type'],
            frequency           = data['frequency'],
            num_simulations     = data.get('num_simulations', 1000),
            binding_conserved   = data.get('binding_conserved', 0.0),
            binding_reduced     = data.get('binding_reduced', 0.0),
            binding_lost        = data.get('binding_lost', 0.0),
            population_coverage = data.get('population_coverage', 0.0),
            ai_insight          = data.get('ai_insight', '')
        )
        db.session.add(sim)
        db.session.flush()
        for d in data.get('details', []):
            db.session.add(MutationDetail(
                simulation_id = sim.id,
                position      = d.get('position', 0),
                original_base = d.get('original_base', ''),
                mutated_base  = d.get('mutated_base', ''),
                mutation_type = d.get('mutation_type', ''),
                effect        = d.get('effect', ''),
                impact        = d.get('impact', 'Low'),
                score         = d.get('score', 0)
            ))
        db.session.commit()
        return jsonify({'message': 'Simulation saved', 'id': sim.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────
# DIMER ANALYSIS
# ─────────────────────────────────────────

@app.route('/dimers/<int:job_id>', methods=['GET'])
def get_dimers(job_id):
    try:
        results = db.session.query(DimerResult, Primer)\
            .join(Primer, DimerResult.primer_id == Primer.id)\
            .filter(DimerResult.job_id == job_id)\
            .order_by(DimerResult.delta_g.asc()).all()
        return jsonify([{
            'id': r.id,
            'primer_id': r.primer_id,
            'primer_sequence': p.sequence,
            'delta_g': r.delta_g,
            'complementarity': r.complementarity,
            'stability_score': r.stability_score,
            'risk_level': r.risk_level,
            'ai_analysis': r.ai_analysis,
            'created_at': r.created_at.strftime('%d %b %Y %H:%M')
        } for r, p in results]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/dimers', methods=['POST'])
def save_dimer_result():
    try:
        data     = request.get_json()
        required = ['job_id', 'primer_id', 'delta_g', 'risk_level']
        if not data or not all(k in data for k in required):
            return jsonify({'error': 'Missing required fields'}), 400
        result = DimerResult(
            job_id          = data['job_id'],
            primer_id       = data['primer_id'],
            delta_g         = data['delta_g'],
            complementarity = data.get('complementarity', 0),
            stability_score = data.get('stability_score', 0),
            risk_level      = data['risk_level'],
            ai_analysis     = data.get('ai_analysis', '')
        )
        db.session.add(result)
        db.session.commit()
        return jsonify({'message': 'Dimer result saved', 'id': result.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────

@app.route('/dashboard/<int:user_id>', methods=['GET'])
def get_dashboard(user_id):
    try:
        job = AnalysisJob.query.filter_by(user_id=user_id)\
            .order_by(AnalysisJob.created_at.desc()).first()
        if not job:
            return jsonify({
                'has_data': False,
                'total_analyses': 0,
                'total_primers': 0,
                'recent_jobs': []
            }), 200
        primers       = Primer.query.filter_by(job_id=job.id).all()
        scores        = [p.robustness_score for p in primers]
        avg_score     = round(sum(scores) / len(scores), 1) if scores else 0
        total_jobs    = AnalysisJob.query.filter_by(user_id=user_id).count()
        total_primers = Primer.query.filter_by(user_id=user_id).count()
        recent_jobs   = AnalysisJob.query.filter_by(user_id=user_id)\
            .order_by(AnalysisJob.created_at.desc()).limit(5).all()
        return jsonify({
            'has_data': True,
            'latest_job': {
                'id': job.id, 'name': job.name,
                'sequence_length': job.sequence_length,
                'primer_count': len(primers),
                'avg_robustness': avg_score,
                'created_at': job.created_at.strftime('%d %b %Y %H:%M')
            },
            'total_analyses': total_jobs,
            'total_primers': total_primers,
            'recent_jobs': [{
                'id': j.id, 'name': j.name,
                'sequence_length': j.sequence_length,
                'primer_count': Primer.query.filter_by(job_id=j.id).count(),
                'created_at': j.created_at.strftime('%d %b %Y %H:%M')
            } for j in recent_jobs]
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────
# PRIMER GENERATOR HELPER
# ─────────────────────────────────────────

def _gc(seq):
    return round((seq.count('G') + seq.count('C')) / len(seq) * 100, 1)

def _tm(seq):
    a = seq.count('A'); t = seq.count('T')
    g = seq.count('G'); c = seq.count('C')
    return round(2 * (a + t) + 4 * (g + c), 1)

def _self_comp(seq):
    rev_comp = seq[::-1].translate(str.maketrans('ATGC', 'TACG'))
    score    = sum(1 for a, b in zip(seq, rev_comp) if a == b)
    return round(score * 0.5, 1)

def _three_comp(seq):
    end3  = seq[-5:]
    rev   = end3[::-1].translate(str.maketrans('ATGC', 'TACG'))
    score = sum(1 for a, b in zip(end3, rev) if a == b)
    return round(score * 0.4, 1)

def _robustness(seq, gc, tm, sc, tc, job):
    score = 100
    if not (job.gc_min <= gc <= job.gc_max):   score -= 20
    if not (job.tm_min <= tm <= job.tm_max):   score -= 15
    if sc > job.max_self_comp:                 score -= 15
    if tc > job.max_three_comp:                score -= 10
    for base in 'ATGC':
        if base * 4 in seq:                    score -= 8
    return max(30, score)

def _generate_primers(job):
    seq     = job.sequence
    primers = []
    seen    = set()
    for length in range(job.primer_len_min, job.primer_len_max + 1):
        step = max(1, length // 3)
        for i in range(0, len(seq) - length + 1, step):
            sub = seq[i:i + length]
            if sub in seen:
                continue
            seen.add(sub)
            gc = _gc(sub)
            tm = _tm(sub)
            if not (job.gc_min <= gc <= job.gc_max): continue
            if not (job.tm_min <= tm <= job.tm_max): continue
            sc = _self_comp(sub)
            tc = _three_comp(sub)
            rb = _robustness(sub, gc, tm, sc, tc, job)
            primers.append(Primer(
                job_id=job.id, user_id=job.user_id,
                sequence=sub, length=length,
                gc_percent=gc, tm=tm,
                self_comp=sc, three_comp=tc,
                robustness_score=rb,
                position=i, strand='forward'
            ))
            if len(primers) >= 120:
                return sorted(primers, key=lambda p: p.robustness_score, reverse=True)
    return sorted(primers, key=lambda p: p.robustness_score, reverse=True)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
