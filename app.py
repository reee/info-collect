from collections import defaultdict
import re
from flask import Flask, current_app, render_template, redirect, send_file, send_from_directory, url_for, request, flash, session
from flask_login import LoginManager, login_user, logout_user, current_user
from flask_bootstrap import Bootstrap5
from flask_migrate import Migrate
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError


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
            session['is_admin'] = True
            session['logged_in'] = True  # 添加通用登录状态标记
            return redirect(url_for('admin_dashboard'))
        else:
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                # 普通用户登录
                login_user(user)
                session['logged_in'] = True
                session['is_admin'] = False
                return redirect(url_for('user_dashboard'))
            else:
                flash('用户名或密码错误', 'danger')
    return render_template('index.html', form=form)

@app.route('/logout')
def logout():
    session.clear()  # 清除所有session数据
    logout_user()    # 清除Flask-Login的用户会话
    return redirect(url_for('login'))

@app.route('/admin')
def admin_dashboard():
    # 检查是否是管理员
    if not session.get('is_admin', False):
        flash('请以管理员身份登录', 'warning')
        return redirect(url_for('login'))

    # 获取所有用户并分组
    users = User.query.all()
    grouped_users = defaultdict(list)

    if users:
        # 获取每个班级的学生人数
        student_counts = dict(db.session.query(Student.class_name, func.count(Student.id))
                              .group_by(Student.class_name).all())

        for user in users:
            # 为用户添加学生人数属性
            user.student_count = student_counts.get(user.username, 0)

            if user.username.startswith(('GZJD', 'CZJD')):
                grouped_users['创新基地班组'].append(user)
            elif user.username.startswith('GZ'):
                match = re.match(r'GZ(\d{4})', user.username)
                if match:
                    year = match.group(1)
                    grouped_users[f'高中{year}届'].append(user)
                else:
                    grouped_users['其他高中'].append(user)
            elif user.username.startswith('CZ'):
                match = re.match(r'CZ(\d{4})', user.username)
                if match:
                    year = match.group(1)
                    grouped_users[f'初中{year}届'].append(user)
                else:
                    grouped_users['其他初中'].append(user)
            else:
                grouped_users['其他'].append(user)

    return render_template('admin_dashboard.html', grouped_users=grouped_users)

@app.route('/import_users', methods=['GET', 'POST'])
def import_users():
    # 检查是否是管理员
    if not session.get('is_admin', False):
        flash('请以管理员身份登录', 'warning')
        return redirect(url_for('login'))

    form = ImportForm()
    if form.validate_on_submit():
        file = form.file.data
        clear_users = form.clear_users.data
        if file.filename.endswith('.xlsx'):
            try:
                if clear_users:
                    # 删除所有现有用户
                    User.query.delete()
                    db.session.commit()
                    flash('所有现有用户已被删除', 'info')

                df = pd.read_excel(file)
                for _, row in df.iterrows():
                    username = row['用户名']
                    password = row['密码']
                    user = User(username=username)
                    user.set_password(password)
                    db.session.add(user)
                db.session.commit()
                flash('用户信息导入成功', 'success')
                return redirect(url_for('admin_dashboard'))
            except Exception as e:
                db.session.rollback()
                flash(f'导入失败：{str(e)}', 'danger')
        else:
            flash('仅支持导入.xlsx文件', 'danger')

    return render_template('import_users.html', form=form)

@app.route('/initialize_system')
def initialize_system():
    # 检查是否是管理员
    if not session.get('is_admin', False):
        flash('请以管理员身份登录', 'warning')
        return redirect(url_for('login'))

    try:
        # 删除所有学生记录
        Student.query.delete()
        db.session.commit()

        # 删除uploads目录下的所有文件
        upload_dir = app.config['UPLOAD_FOLDER']
        for filename in os.listdir(upload_dir):
            if filename != '.gitkeep':  # 保留.gitkeep文件
                file_path = os.path.join(upload_dir, filename)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print(f'Error deleting {file_path}: {e}')

        flash('系统已成功初始化：所有学生信息和照片已被清除', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'初始化失败：{str(e)}', 'danger')

    return redirect(url_for('admin_dashboard'))

@app.route('/user')
def user_dashboard():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    student_entries = Student.query.filter_by(class_name=current_user.username).all()
    return render_template('user_dashboard.html', current_user=current_user, student_entries=student_entries)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/add_student', methods=['GET', 'POST'])
def add_student():
    form = StudentForm()
    if request.method == 'POST':
        if form.validate_on_submit():
            # 检查同班是否存在同名学生
            existing_student = Student.query.filter_by(
                name=form.name.data,
                class_name=current_user.username
            ).first()
            
            if existing_student:
                flash('当前本班已存在同名学生。若需要修改相关信息，请先删除对应学生后再添加。若确实存在同名情况，可在名字后加上数字或其他后缀后再添加。', 'warning')
                return redirect(url_for('user_dashboard'))

            photo_filename = None
            if form.photo.data:
                try:
                    # 读取图片并进行处理
                    image = Image.open(form.photo.data)
                    
                    # 获取旋转角度并应用旋转
                    rotation = request.form.get('rotation', '0')
                    if rotation and rotation != '0':
                        # 转换为整数并取负值（因为前端顺时针旋转，而PIL逆时针旋转）
                        rotation_angle = -int(rotation)
                        image = image.rotate(rotation_angle, expand=True)
                    
                    # 生成唯一文件名
                    photo_filename = str(uuid.uuid4()) + '.jpg'
                    
                    # 调整图片大小并保持纵横比
                    max_size = (800, 800)
                    image.thumbnail(max_size, Image.Resampling.LANCZOS)
                    
                    # 保存处理后的图片
                    image_path = os.path.join(app.config['UPLOAD_FOLDER'], photo_filename)
                    image = image.convert('RGB')  # 确保保存为JPG格式
                    image.save(image_path, 'JPEG', quality=85)
                except Exception as e:
                    current_app.logger.error(f"Image processing error: {str(e)}")
                    flash('图片处理失败，请确保上传了有效的图片文件', 'danger')
                    return redirect(url_for('add_student'))

            # 创建新的学生对象
            student = Student(
                name=form.name.data,
                class_name=current_user.username,
                gender=form.gender.data,
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
            for student in students:
                student.internal_id = None
                db.session.commit()  # 提交清空操作

            prefix_map = {
                'GZJD': '30',
                'CZJD': '40',
                'GZ': '20',
                'CZ': '10'
            }

            try:
                for idx, student in enumerate(students, start=1):
                    for prefix, num in prefix_map.items():
                        if current_user.username.startswith(prefix):
                            slice_index = len(prefix) + 2
                            internal_id = f"{num}{current_user.username[slice_index:]}{idx:02d}"
                            student.internal_id = str(internal_id)
                            #current_app.logger.info(f"Student {student.name} assigned internal_id: {internal_id}")
                            break
                
                db.session.commit()
                flash('学生信息添加成功', 'success')
                return redirect(url_for('user_dashboard'))

            except SQLAlchemyError as e:
                db.session.rollback()
                flash('数据库操作失败，请稍后重试', 'error')
                # 可以添加日志记录
                current_app.logger.error(f"Database error: {str(e)}")
                return redirect(url_for('error_page'))
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

@app.route('/export_class_students/<username>/<boarding_or_leaving>', methods=['GET'])
def export_class_students(username, boarding_or_leaving):
    if boarding_or_leaving == 'True':
        students = Student.query.filter_by(class_name=username, boarding_student=True).all()
        file_suffix = '住校'
    elif boarding_or_leaving == 'False':
        students = Student.query.filter_by(class_name=username, boarding_student=False).all()
        file_suffix = '非住校'
    elif boarding_or_leaving == 'leaving':
        students = Student.query.filter_by(class_name=username, noon_leaving=True, night_leaving=True).all()
        file_suffix = '中午晚上离校'
    else:
        flash('无效的导出选项', 'error')
        return redirect(url_for('admin_dashboard'))
    
    if not students:
        flash(f'没有找到 {username} 班级的{file_suffix}学生。', 'info')
        return redirect(url_for('admin_dashboard'))

    # 创建一个工作簿
    wb = Workbook()
    ws = wb.active
    ws.title = "学生信息"
    
    # 添加表头
    ws.append(["班级", "姓名", "内部编号", "性别", "中午出校", "晚上出校", "校内走读", "住校", "备注"])
    
    # 添加学生信息
    for student in students:
        ws.append([
            student.class_name,
            student.name,
            student.internal_id,
            student.gender,
            "是" if student.noon_leaving else "否",
            "是" if student.night_leaving else "否",
            "是" if student.day_student else "否",
            "是" if student.boarding_student else "否",
            student.remarks
        ])
    
    # 保存Excel文件
    excel_buffer = io.BytesIO()
    wb.save(excel_buffer)
    excel_buffer.seek(0)

    # 创建一个zip文件并添加Excel文件
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.writestr("students_list.xlsx", excel_buffer.getvalue())

        # 添加学生照片
        for student in students:
            if student.photo_filename:
                photo_path = os.path.join(app.config['UPLOAD_FOLDER'], student.photo_filename)
                photo_name = f"{student.name}_{student.internal_id}.jpg"
                with open(photo_path, 'rb') as photo_file:
                    zipf.writestr(photo_name, photo_file.read())

    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        as_attachment=True,
        download_name=f"{username}_{file_suffix}_students.zip"
    )

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
