from flask import Flask, render_template, redirect, send_file, url_for, request, flash
from flask_login import LoginManager, login_user, logout_user, current_user
from flask_bootstrap import Bootstrap5
from flask_migrate import Migrate

from forms import LoginForm, ImportForm, StudentForm
from models import db, User, Student

import json
import uuid
import os
import pandas as pd
from PIL import Image
from openpyxl import Workbook
import zipfile
import io

import logging
from logging.handlers import RotatingFileHandler

# 创建日志记录器
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# 创建文件处理器并设置日志级别
file_handler = RotatingFileHandler('app.log', maxBytes=1024 * 1024, backupCount=10)
file_handler.setLevel(logging.DEBUG)

# 创建格式化器并将其添加到文件处理器
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# 将文件处理器添加到日志记录器
logger.addHandler(file_handler)

app = Flask(__name__)
bootstrap = Bootstrap5(app)
app.config['SECRET_KEY'] = 'jBTyx35KZhj7Ljhb93rWGQHDrHXRKD'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///info-collect.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['BOOTSTRAP_SERVE_LOCAL'] = True

migrate = Migrate(app, db)

# Initialize database
db.init_app(app)
login_manager = LoginManager(app)

@login_manager.user_loader
def load_user(user_id):
    # 查询数据库，根据 user_id 返回相应的用户对象
    user = User.query.get(user_id)
    if user is None:
        return None
    return user

# Load admin credentials from config file
with open('admin_config.json') as f:
    admin_config = json.load(f)

@app.route('/', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        if username == admin_config['username'] and password == admin_config['password']:
            # Admin login
            return redirect(url_for('admin_dashboard'))
        else:
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
            # 普通用户登录
                login_user(user)
                return redirect(url_for('user_dashboard'))
            else:
                flash('用户名或密码错误', 'danger')
    return render_template('index.html', form=form)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/admin', methods=['GET', 'POST'])
def admin_dashboard():
    form = ImportForm()
    if form.validate_on_submit():
        file = form.file.data
        if file.filename.endswith('.xlsx'):
            try:
                df = pd.read_excel(file)
                for _, row in df.iterrows():
                    username = row['用户名']
                    password = row['密码']
                    user = User(username=username)
                    user.set_password(password)
                    db.session.add(user)
                db.session.commit()
                flash('用户信息导入成功', 'success')
            except Exception as e:
                flash(f'导入失败：{str(e)}', 'danger')
        else:
            flash('仅支持导入.xlsx文件', 'danger')
    return render_template('admin_dashboard.html', form=form)

@app.route('/user')
def user_dashboard():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    student_entries = Student.query.filter_by(class_name=current_user.username).all()
    return render_template('user_dashboard.html', current_user=current_user, student_entries=student_entries)

@app.route('/add_student', methods=['GET', 'POST'])
def add_student():
    form = StudentForm()
    if request.method == 'POST':
        if form.validate_on_submit():
            if form.photo.data:
                photo_filename = str(uuid.uuid4()) + '.' + form.photo.data.filename.split('.')[-1]
                image = Image.open(form.photo.data)
                image.thumbnail((800, 600))
                image.save(os.path.join(app.config['UPLOAD_FOLDER'], photo_filename))

            # 创建新的学生对象
            student = Student(
                name=form.name.data,
                class_name=current_user.username,
                noon_leaving=form.noon_leaving.data,
                night_leaving=form.night_leaving.data,
                day_student=form.day_student.data,
                boarding_student=form.boarding_student.data,
                remarks=form.remarks.data,
                photo_filename=photo_filename
            )
            db.session.add(student)
            db.session.commit()

            # 对本班级的所有学生进行排序编号
            students = Student.query.filter_by(class_name=current_user.username).order_by(Student.name).all()
            for idx, student in enumerate(students, start=1):
                # 初中部分逻辑尚未实现
                if current_user.username.startswith('G'):
                    internal_id = current_user.username[1:] + '{:02d}'.format(idx)
                    student.internal_id = internal_id
                db.session.commit()

            flash('学生信息添加成功', 'success')
            return redirect(url_for('user_dashboard'))
        else:
        # 如果表单验证失败，显示错误消息并返回到表单页面
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f'字段 "{getattr(form, field).label.text}"：{error}', 'danger')
            return redirect(url_for('add_student'))  # 重定向到添加学生页面

    return render_template('add_student.html', form=form)

@app.route('/edit_student/<int:student_id>', methods=['GET', 'POST'])
def edit_student(student_id):
    student = Student.query.get_or_404(student_id)
    form = StudentForm(obj=student)
    if form.validate_on_submit():
        # 更新学生信息
        form.populate_obj(student)
        db.session.commit()
        flash('学生信息更新成功', 'success')
        return redirect(url_for('user_dashboard'))
    return render_template('edit_student.html', form=form, student=student)

@app.route('/delete_student/<int:student_id>', methods=['POST'])
def delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    db.session.delete(student)
    db.session.commit()
    photo_path = os.path.join(app.config['UPLOAD_FOLDER'], student.photo_filename)
    if os.path.exists(photo_path):
        os.remove(photo_path)
    flash('学生信息删除成功', 'success')
    return redirect(url_for('user_dashboard'))

@app.route('/export_students', methods=['GET'])
def export_students():
    students = Student.query.all()
    
    # 创建一个工作簿
    wb = Workbook()
    ws = wb.active
    ws.title = "学生信息"
    
    # 添加表头
    ws.append(["班级", "姓名", "内部编号", "中午出校", "晚上出校", "校内走读", "住校", "备注"])
    
    # 添加学生信息
    for student in students:
        ws.append([
            student.class_name,
            student.name,
            student.internal_id,
            "是" if student.noon_leaving else "否",
            "是" if student.night_leaving else "否",
            "是" if student.day_student else "否",
            "是" if student.boarding_student else "否",
            student.remarks
        ])
    
    # 保存文件
    filename = "students.xlsx"
    wb.save(filename)
    
    # 提供文件下载
    return send_file(filename, as_attachment=True)

@app.route('/export_student_photos', methods=['GET'])
def export_student_photos():
    students = Student.query.all()
    
    # 创建一个内存缓冲区来保存 zip 文件
    zip_buffer = io.BytesIO()
    
    # 创建一个 zip 压缩包
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # 将学生照片添加到 zip 压缩包中
        for student in students:
            if student.photo_filename:
                photo_path = os.path.join(app.config['UPLOAD_FOLDER'], student.photo_filename)
                photo_name = f"{student.name}_{student.internal_id}.jpg"  # 学生姓名+内部编号作为照片名称
                # 将照片文件内容直接写入到 zip 压缩包中
                with open(photo_path, 'rb') as photo_file:
                    zipf.writestr(photo_name, photo_file.read())
    
    # 将内存缓冲区的内容作为文件发送给用户以供下载
    zip_buffer.seek(0)
    return send_file(zip_buffer, as_attachment=True, download_name='student_photos.zip')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
