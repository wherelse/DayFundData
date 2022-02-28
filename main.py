import configparser
import json
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import parseaddr, formataddr
import requests
import markdown
import time
import copy


# 获取配置文件
def read_ini_config():
    """
    读取相关配置文件
    :return: 返回配置文件内容
    """
    config_data = configparser.ConfigParser()
    config_data.read("./config.ini", encoding="utf-8")
    return config_data


# 邮件信息格式化


def _format_addr(s):
    """
    格式化字符串为邮件格式
    :param s: 输入的字符串
    :return: 返回格式化完成的字符串
    """
    name, addr = parseaddr(s)
    return formataddr((Header(name, 'utf-8').encode(), addr))


# 邮件发送


def send_mail(msg, config_data):
    """
    邮件发送函数
    :param msg:发送的文件内容，包括标题，邮件内容
    :param config_data: 收发件人信息，smtp邮箱配置
    :return:
    """
    message = MIMEText(msg['content'], 'html', 'utf-8')  # 将邮件内容转换为MIMEText格式
    sendaddr = config_data['mailconfig']['send_address']
    receive_addr = config_data['mailconfig']['receive_address']
    name = config_data['mailconfig']['username']
    message['From'] = _format_addr(name + '<%s>' % sendaddr)  # 设置发件人姓名和邮箱地址
    message['To'] = _format_addr(receive_addr)
    message['Subject'] = Header(msg['mailtitle'], 'utf-8').encode()  # 设置邮件标题

    # 登录邮箱并发送邮件
    try:
        smtp = smtplib.SMTP_SSL(config_data['mailconfig']
                                ['mailhost'], config_data['mailconfig']['port'])
        smtp.login(sendaddr, config_data['mailconfig']['password'])
        smtp.sendmail(sendaddr, receive_addr, message.as_string())
        smtp.quit()
        print('邮件发送成功')
    except smtplib.SMTPException:
        print('Error: 邮件发送失败')


def md2html(mdstr):
    """
    markdown 转换 html函数，将markdown表格转换为带样式的html邮件
    :param mdstr: 需要转换的内容
    :return: 返回html邮件内容
    """
    with open('./template.htm', 'r', encoding='utf-8') as f:
        html = f.read()
    mdcontent = markdown.markdown(mdstr['content'], extensions=['tables'])
    index = mdcontent.find('<table>')
    mdcontent_style = mdcontent[:index + 6] + \
                      ' style="width: 90%;margin: 0 auto;font-size: 18px"' + \
                      mdcontent[index + 6:]

    start = 0
    while True:
        index = mdcontent_style.find('<td', start)
        if index > -1:
            mdcontent_style = mdcontent_style[:index + 3] + \
                              ' style="padding:10px"' + mdcontent_style[index + 3:]
            start = index + 1
        else:
            break

    start = 0
    while True:
        index = mdcontent_style.find('<th', start)
        if index > -1:
            mdcontent_style = mdcontent_style[:index + 3] + \
                              ' style="padding:10px;"' + mdcontent_style[index + 3:]
            start = index + 1
        else:
            break
    html = html.replace('{{title}}', mdstr['mailtitle'])
    html = html.replace('{{content}}', mdcontent_style)
    html = html.replace('{{time}}', mdstr['time'])
    return html


# severchan通知


def serverchan(msg, config_data):
    url = 'https://sctapi.ftqq.com/'
    title = msg['mailtitle']
    content = msg['content']
    pushkey = config_data['serverchan']['sendkey']
    pushchannel = config_data['serverchan']['pushchannel']
    try:
        requests.post(url + pushkey + '.send', data={'text': title, 'desp': content, 'channel': pushchannel}, headers={
            'Content-type': 'application/x-www-form-urlencoded'}, timeout=1)
    except requests.exceptions.RequestException as e:
        print('Error: serverchan通知失败')
        raise SystemExit(e)


# 获取基金信息
def get_fund_rawdata(config_data):
    url = 'https://api.doctorxiong.club/v1/fund?code='
    fund_id = config_data['fund']['fund_id']
    try:
        req_result = requests.get(url + fund_id, timeout=1)
        result = json.loads(req_result.text)
        if result['code'] != 200 and config_data['serverchan']['error_report'] == 'true':
            message = {'content': '基金信息获取失败', 'mailtitle': '交易日二点半基金涨跌信息'}
            serverchan(message, config_data)
            raise SystemExit('Error: 获取基金信息失败')
        return result
    except requests.exceptions.RequestException as e:
        message = {'content': '基金信息获取失败', 'mailtitle': '交易日二点半基金涨跌信息'}
        if config_data['severchan']['error_report'] == 'true':
            serverchan(message, config_data)
        print('基金信息获取失败')
        raise SystemExit(e)


# 基金信息处理-获取涨跌幅


def fund_rawdata_process(fund_raw_data):
    fund_info = []
    for data in fund_raw_data['data']:
        fund_msg = {'name': data['name'], 'growth_rate': data['expectGrowth']}
        fund_info.append(fund_msg)
    return fund_info


def get_time():
    _date = time.strftime('%Y-%m-%d', time.localtime())
    _time = time.strftime('%H:%M:%S', time.localtime())
    return _date, _time


def send_reminder(fund_info, config):
    date, times = get_time()
    # 填充发送内容
    msgtitle = '交易日二点半基金涨跌信息'
    sendmsg = '|基金名称|涨跌幅|\n|:---:|:---:|\n'
    for data in fund_info:
        sendmsg += f'|{data["name"]}|{data["growth_rate"]}%|\n'
    sendmsg_content = {'content': sendmsg,
                       'mailtitle': msgtitle, 'time': date + ' ' + times}
    serverchan_content = copy.deepcopy(sendmsg_content)
    mail_content = copy.deepcopy(sendmsg_content)
    mail_content['content'] = md2html(mail_content)
    serverchan_content['content'] = f'### 时间：{serverchan_content["time"]}' + '\n\n' + \
                                    serverchan_content['content']

    reminderpath = config['reminder_config']['reminder_path']
    # with open("save.html", "wb") as f:
    #     #   写文件用bytes而不是str，所以要转码
    #     f.write(mail_content['content'].encode('utf-8'))
    if reminderpath == 'both':
        serverchan(serverchan_content, config)
        send_mail(mail_content, config)
    elif reminderpath == 'serverchan':
        serverchan(serverchan_content, config)
    elif reminderpath == 'mail':
        send_mail(mail_content, config)


def main_handler():
    configs = read_ini_config()
    fund_rawdata = get_fund_rawdata(configs)
    fund_infos = fund_rawdata_process(fund_rawdata)
    send_reminder(fund_infos, configs)
    print('finished\n')


if __name__ == '__main__':
    main_handler()
