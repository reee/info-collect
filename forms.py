from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import SelectField, StringField, BooleanField, TextAreaField, SubmitField, PasswordField, HiddenField
from wtforms.validators import DataRequired, Length

class StudentForm(FlaskForm):
    name = StringField('姓名', validators=[DataRequired(), Length(max=20)])
    gender = SelectField('性别', choices=[('男', '男'), ('女', '女')], validators=[DataRequired()])
    noon_leaving = BooleanField('中午离校')
    night_leaving = BooleanField('晚上离校')
    day_student = BooleanField('校内走读')
    boarding_student = BooleanField('住校')
    remarks = TextAreaField('备注', validators=[Length(max=255)])
    photo = FileField('上传照片', validators=[DataRequired(), FileAllowed(['jpg', 'jpeg'], '只能上传jpg或jpeg图片文件')])
    submit = SubmitField('提交')

class LoginForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired(), Length(max=100)])
    password = PasswordField('密码', validators=[DataRequired()])
    submit = SubmitField('登录')

class ImportForm(FlaskForm):
    file = FileField('上传用户信息文件', validators=[DataRequired()])
    clear_users = BooleanField('清空现有用户') 
    submit = SubmitField('导入')
