from os import path, walk, getenv
from sys import argv, exit
from time import time, strftime, localtime, sleep
from requests import post, put, get
import requests
from zipfile import ZipFile
from io import BytesIO
import subprocess

from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QAction, QLabel, QDialog, QTextEdit, QStackedWidget, QFileDialog
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QTextCursor

from my_tips import find_txts, extract_md, data_to_json, path_check

# 优先加载 .env（若安装了 python-dotenv）
try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore
    _env_path = find_dotenv()
    if _env_path:
        load_dotenv(_env_path, override=False)
except Exception:
    pass
from my_styles import choose_font, choose_style
from my_dialogs_com import HTMLDialog, StateDialog
from my_dialogs_DMH import MinerUAPIDialog, MinerUFolderDialog


class MinerUWorker(QThread):
    """MinerU工作线程类"""
    
    id_text = pyqtSignal(str)
    update_text = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    update_status = pyqtSignal(str)

    finished_signal = pyqtSignal(dict)
    
    def __init__(self, main_window, api_key, pdf_folder_path, md_folder_path, txt_folder_path):
        """初始化线程类"""

        super().__init__()

        self.main_window = main_window
        # 这里接收主窗口传入的 api_key（可能来自 .env 或手动输入）
        self.api_key = api_key
        self.pdf_folder_path = pdf_folder_path
        self.md_folder_path = md_folder_path
        self.txt_folder_path = txt_folder_path
        
        self.log_json = []
        
    def run(self):
        """运行线程"""

        try:
            self.run_mineru_task()
        except Exception as e:
            self.error_signal.emit(f"Error in MinerU task: {str(e)}")
    
    def run_mineru_task(self):
        """执行 MinerU 任务"""

        self.update_text.emit("------------------------------------\n")
        
        start_time = time()
        self.update_text.emit("<b>Start Time:</b>")
        self.update_text.emit(f"{strftime('%Y-%m-%d %H:%M:%S', localtime())}\n")

        all_pdf_file_paths = find_txts(self.pdf_folder_path, extension='.pdf')
        # 排序以确保 0001.pdf, 0002.pdf ... 的顺序一致
        all_pdf_file_paths = sorted(all_pdf_file_paths, key=lambda p: path.basename(p))

        # 采样控制：支持通过环境变量限制起始与条数（MINERU_START/MINERU_LIMIT）
        try:
            start_idx = int(getenv('MINERU_START') or 0)
        except Exception:
            start_idx = 0
        try:
            limit_cnt = int(getenv('MINERU_LIMIT') or 0)
        except Exception:
            limit_cnt = 0
        if start_idx < 0:
            start_idx = 0
        if limit_cnt and limit_cnt > 0:
            all_pdf_file_paths = all_pdf_file_paths[start_idx:start_idx + limit_cnt]
        elif start_idx:
            all_pdf_file_paths = all_pdf_file_paths[start_idx:]

        if not all_pdf_file_paths:
            self.error_signal.emit("PDF file not found!")
            return
        
        chunk_pdf_file_paths = [all_pdf_file_paths[i:i + 190] for i in range(0, len(all_pdf_file_paths), 190)]
        # MinerU API 单次最多处理 200 个 pdf 文件，保守使用 190 进行分块

        for chunk_index, pdf_file_paths in enumerate(chunk_pdf_file_paths):
        
            pdf_file_names = [path.basename(pdf_file_path) for pdf_file_path in pdf_file_paths]
            self.update_text.emit(
                f"There are {len(pdf_file_names)} pdf files in Chunk {chunk_index} of\n{self.pdf_folder_path}\n"
            )

            data = {
                "enable_formula": True,
                "enable_table": True,
                "language": "ch",
                "files": [
                    {"name": pdf_file_name, "is_ocr": False, "data_id": "abcd"} for pdf_file_name in pdf_file_names
                ],
            }    # 需要定期查阅 MinerU 官方文档是否对参数的设定做出了更改 (https://mineru.net/apiManage/docs)
                        
            try:

                response = post(
                    url="https://mineru.net/api/v4/file-urls/batch",
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
                    json=data,
                )

                if response.status_code == 200:

                    result = response.json()
                    self.update_text.emit("<b>Requests successful.</b>")
                    self.update_text.emit("")

                    if result["code"] == 0:

                        batch_ID = result["data"]["batch_id"]
                        self.id_text.emit(str(batch_ID))
                        self.update_text.emit(f"<b>Batch ID: {batch_ID}</b>")
                        self.update_text.emit("")

                        file_urls = result["data"]["file_urls"]

                        if len(file_urls) != len(pdf_file_paths):
                            self.update_text.emit(
                                "The number of URLs does not match the number of file paths! "
                                "Please carefully verify after the processing is completed!\n"
                            )

                        for index, file_url in enumerate(result["data"]["file_urls"]):

                            with open(pdf_file_paths[index], 'rb') as f:
                                res_upload = put(file_url, data=f)

                            if res_upload.status_code == 200:
                                self.update_text.emit(f"{pdf_file_names[index]} uploaded successfully.\n")
                            else:
                                self.update_text.emit(f"{pdf_file_names[index]} uploaded failed!\n")

                    else:
                        self.error_signal.emit(f"Failed to enable URL upload! Error:\n{result.msg}")
                        return

                else:
                    self.error_signal.emit(
                        f"Requests failed!\nStatus: {response.status_code}\nResponse: {response}\n"
                    )
                    return
                            
            except Exception as e:
                self.error_signal.emit(f"Error for requests:\n{e}\n")
                return

            check_condition = True
            task_start_time = time()

            while check_condition:

                try:

                    res = get(
                        f"https://mineru.net/api/v4/extract-results/batch/{batch_ID}",
                        headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
                    )

                    states = [infos['state'] for infos in res.json()['data']['extract_result']]

                    if all(state in {'done', 'failed'} for state in states):

                        self.update_text.emit("<b>Processing completed!</b>")
                        self.update_text.emit("")

                        for infos in res.json()['data']['extract_result']:

                            if infos['err_msg']:
                                self.update_text.emit(
                                    f"Failed to process {infos['file_name']}!\nError: {infos['err_msg']}\n"
                                )

                            else:

                                download_file_path = path.join(self.md_folder_path, infos["file_name"][:-4])
                                file_url = infos["full_zip_url"]
                                ok = self._download_and_extract(file_url, download_file_path)
                                if ok:
                                    self.update_text.emit(
                                        f"{infos['file_name']} has been downloaded to:\n{download_file_path}\n"
                                    )
                                else:
                                    short = file_url.split("/pdf/")[-1] if "/pdf/" in file_url else file_url[-80:]
                                    self.update_text.emit(
                                        f"{infos['file_name']} was not downloaded!\nLink: ...{short}\n"
                                    )

                        check_condition = False
                        
                    else:

                        self.update_text.emit("Processing......\nThe status will be checked after 10 s.....\n")

                        if time() - task_start_time > 3600:  
                            self.error_signal.emit("Timeout: Processing time exceeded 60 min!")
                            return
                        
                        sleep(10)
                    
                except Exception as e:
                    self.error_signal.emit(f"Error for requests:\n{e}")
                    return
                
            for root, dirs, files in walk(self.md_folder_path):

                for dir_name in dirs:
                    
                    md_file_path = path.join(root, dir_name, 'full.md')

                    if path.exists(md_file_path):
                        
                        txt_name = dir_name
                        txt_file_name = f"{txt_name}.txt"
                        txt_file_path = path.join(self.txt_folder_path, txt_file_name)

                        with open(md_file_path, 'r', encoding='utf-8') as md_file:
                            content = md_file.readlines()

                        raw_dir = path.join(root, dir_name)
                        result_info = extract_md(txt_name, content, txt_file_path, raw_dir)
                        self.log_json.append(result_info)
                        md_out_path = result_info.get('md_path', txt_file_path[:-4] + '.md')
                        self.update_text.emit(
                            f"Conversion completed!\nMD: {md_out_path}\nTXT: {txt_file_path}\n"
                        )

        data_to_json(self.txt_folder_path, self.log_json)

        self.update_text.emit("<b>End Time:</b>")
        self.update_text.emit(f"{strftime('%Y-%m-%d %H:%M:%S', localtime())}\n")
        self.update_text.emit("<b>Processing Time:</b>")
        self.update_text.emit(f"{(time() - start_time) / 60:.2f} min\n")
        
        result_data = {"log_json": self.log_json, "processing_time": (time() - start_time) / 60}
        self.finished_signal.emit(result_data)

    # 稳定下载 ZIP 并解压：带重试与 curl 兜底，规避 SSL EOF
    def _download_and_extract(self, zurl: str, out_dir: str, max_retries: int = 6) -> bool:
        try:
            path_check(out_dir)
        except Exception:
            return False
        # 简短链接片段用于日志
        short = zurl.split("/pdf/")[-1] if "/pdf/" in zurl else zurl[-80:]
        try:
            self.update_text.emit(f"Downloading ZIP: ...{short}")
        except Exception:
            pass
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/zip,application/octet-stream,*/*;q=0.8",
            "Connection": "close",
        }
        delay = 1
        for _ in range(max_retries):
            for verify in (True, False):
                try:
                    try:
                        self.update_text.emit(f" - try with verify={'on' if verify else 'off'}")
                    except Exception:
                        pass
                    r = requests.get(zurl, headers=headers, timeout=180, stream=True, verify=verify)
                    r.raise_for_status()
                    data = BytesIO()
                    for chunk in r.iter_content(chunk_size=1024 * 128):
                        if chunk:
                            data.write(chunk)
                    data.seek(0)
                    with ZipFile(data) as zf:
                        zf.extractall(out_dir)
                    try:
                        self.update_text.emit(" - ok (requests)")
                    except Exception:
                        pass
                    return True
                except Exception:
                    pass
            sleep(delay)
            delay = min(delay * 2, 32)
        # curl 兜底（不同 TLS 栈）
        try:
            try:
                self.update_text.emit(" - fallback to curl")
            except Exception:
                pass
            tmp_zip = path.join(out_dir, "__mineru_tmp__.zip")
            cmd = [
                "curl", "-L", "--retry", "5", "--connect-timeout", "20", "-m", "180",
                "-H", "Accept: application/zip,application/octet-stream,*/*;q=0.8",
                "-H", "Connection: close",
                "-o", tmp_zip, zurl,
            ]
            rc = subprocess.run(cmd, capture_output=True)
            if rc.returncode != 0 or (not path.exists(tmp_zip)) or path.getsize(tmp_zip) < 128:
                cmd2 = cmd[:]
                cmd2.insert(1, "-k")
                rc2 = subprocess.run(cmd2, capture_output=True)
                if rc2.returncode != 0 or (not path.exists(tmp_zip)) or path.getsize(tmp_zip) < 128:
                    try:
                        self.update_text.emit(" - curl failed")
                    except Exception:
                        pass
                    return False
            with open(tmp_zip, 'rb') as f:
                data = BytesIO(f.read())
            with ZipFile(data) as zf:
                zf.extractall(out_dir)
            try:
                from os import remove
                remove(tmp_zip)
            except Exception:
                pass
            try:
                self.update_text.emit(" - ok (curl)")
            except Exception:
                pass
            return True
        except Exception:
            return False


class MinerUMainWindow(QMainWindow):
    """MinerU主窗口类"""

    ### 界面组件

    def __init__(self):
        """初始化变量"""

        super().__init__()

        # 优先从环境变量读取，其次使用约定默认路径
        # API Key：MINERU_API_KEY；目录：MINERU_PDF_DIR/MINERU_MD_DIR/MINERU_OUT_DIR
        self.api_key = getenv('MINERU_API_KEY') or None

        # 目录默认值（若环境未设置）
        default_pdf = '7-杨皓然-高研院/paper'
        default_md = 'mineru_raw'
        default_out = 'md_clean'

        self.pdf_folder_path = getenv('MINERU_PDF_DIR') or default_pdf
        self.md_folder_path = getenv('MINERU_MD_DIR') or default_md
        self.txt_folder_path = getenv('MINERU_OUT_DIR') or default_out

        # 确保输出目录存在；PDF 目录若不存在则置空，提示用户手动选择
        if self.md_folder_path:
            path_check(self.md_folder_path)
        if self.txt_folder_path:
            path_check(self.txt_folder_path)
        # PDF 目录若不存在，保留字符串但在运行前进行显式校验与报错指引

        self.batch_ID = None
        self.log_json = []

        self.initUI()
    
    def initUI(self):
        """初始化主界面和菜单栏"""

        self.setWindowTitle('DocNerd MinerU Helper')
        self.setGeometry(100, 100, 1600, 900)
        
        icon_path = "Mh.ico"
        if path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        self.create_menu_bar()
        self.create_central_widget()
        
        self.setStyleSheet(choose_style('main window'))       
    
    def create_menu_bar(self):
        """创建菜单栏"""

        menubar = self.menuBar()
        
        platform_menu = menubar.addMenu('MinerU')

        setup_menu = platform_menu.addMenu('Set up')
        
        set_enter_action = QAction('Enter', self)
        set_enter_action.triggered.connect(self.set_up_enter)
        setup_menu.addAction(set_enter_action)

        set_txt_action = QAction('From File', self)
        set_txt_action.triggered.connect(self.set_up_txt)
        setup_menu.addAction(set_txt_action)

        choose_action = QAction('Select Folders', self)
        choose_action.triggered.connect(self.select_folders)
        platform_menu.addAction(choose_action)
        
        run_action = QAction('Run', self)
        run_action.triggered.connect(self.running_mineru)
        platform_menu.addAction(run_action)

        clear_action = QAction('Clear', self)
        clear_action.triggered.connect(self.clear_page)
        platform_menu.addAction(clear_action)
        
        about_menu = menubar.addMenu('About')
        
        about_action = QAction('About DocNerd', self)
        about_action.triggered.connect(self.show_about)
        about_menu.addAction(about_action)
    
    def create_central_widget(self):
        """创建主窗口中心部件"""

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        
        status_layout = QHBoxLayout()
        
        self.api_label = QLabel("API Key: Ready" if self.api_key else "API Key: None")
        self.api_label.setFont(choose_font('h3'))
        self.api_label.setStyleSheet(choose_style('state label'))
        status_layout.addWidget(self.api_label)

        _folders_ready = all([
            bool(self.pdf_folder_path), bool(self.md_folder_path), bool(self.txt_folder_path)
        ]) and path.exists(self.pdf_folder_path) and path.exists(self.md_folder_path) and path.exists(self.txt_folder_path)
        self.folder_label = QLabel("Folder Paths: Ready" if _folders_ready else "Folder Paths: None")
        self.folder_label.setFont(choose_font('h3'))
        self.folder_label.setStyleSheet(choose_style('state label'))
        status_layout.addWidget(self.folder_label)
        
        self.id_label = QLabel("Batch ID: None")
        self.id_label.setFont(choose_font('h3'))
        self.id_label.setStyleSheet(choose_style('state label'))
        status_layout.addWidget(self.id_label)
        
        status_layout.addStretch()
        
        main_layout.addLayout(status_layout)
        
        separator = QLabel()
        separator.setFixedHeight(1)
        separator.setStyleSheet(choose_style('separator'))
        main_layout.addWidget(separator)
        
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setStyleSheet(choose_style('stacked widget'))
        
        self.create_welcome_page()
        self.create_run_page()
        
        self.stacked_widget.setCurrentIndex(0)
        
        main_layout.addWidget(self.stacked_widget)
        
        main_layout.setStretch(0, 0)
        main_layout.setStretch(1, 0)
        main_layout.setStretch(2, 1)
    
    def create_welcome_page(self):
        """创建欢迎页面"""
        
        welcome_page = QWidget()
        welcome_layout = QVBoxLayout(welcome_page)
        welcome_layout.addStretch()
        
        welcome_container = QWidget()
        welcome_container.setFixedSize(1000, 400)
        welcome_container.setStyleSheet(choose_style('widget'))
        
        container_layout = QVBoxLayout(welcome_container)
        
        welcome_title = QLabel("Welcome to\nDocNerd MinerU Helper!")
        welcome_title.setFont(choose_font('h1'))
        welcome_title.setAlignment(Qt.AlignCenter)
        welcome_title.setStyleSheet(choose_style('big label'))
        container_layout.addWidget(welcome_title)
        
        welcome_desc = QLabel("Start by setting up MinerU configuration.")
        welcome_desc.setFont(choose_font('text'))
        welcome_desc.setAlignment(Qt.AlignCenter)
        welcome_desc.setStyleSheet(choose_style('grey mid label'))
        container_layout.addWidget(welcome_desc)
        
        center_layout = QHBoxLayout()
        center_layout.addStretch()
        center_layout.addWidget(welcome_container)
        center_layout.addStretch()
        
        welcome_layout.addLayout(center_layout)
        welcome_layout.addStretch()
        
        self.stacked_widget.addWidget(welcome_page)
    
    def create_run_page(self):
        """创建 Run 页面"""
        
        prompt_page = QWidget()
        prompt_layout = QVBoxLayout(prompt_page)
        prompt_layout.setContentsMargins(20, 20, 20, 20)
        
        content_layout = QVBoxLayout()

        run_label = QLabel("MinerU Status:")
        run_label.setFont(choose_font('label'))
        run_label.setStyleSheet(choose_style('label'))
        content_layout.addWidget(run_label)
        
        self.running_text = QTextEdit()
        self.running_text.setPlaceholderText("Running status of MinerU...")
        self.running_text.setFont(choose_font('text'))
        self.running_text.setStyleSheet(choose_style('text edit'))     
        content_layout.addWidget(self.running_text)

        prompt_layout.addLayout(content_layout)
        self.stacked_widget.addWidget(prompt_page)
    
    ### 状态组件

    def update_state_dialog(self, state, prompt, parent=None):
        """弹出状态对话框"""

        state_dialog = StateDialog(state, prompt, parent)
        state_dialog.exec_()
    
    def update_running_text(self, running_state):
        """更新 MinerU 运行状态消息"""

        self.running_text.append(running_state)
        try:
            self.running_text.moveCursor(QTextCursor.End)
        except Exception:
            pass
        QApplication.processEvents()
    
    def update_id(self, batch_id):
        """更新 MinerU 运行 ID"""

        self.id_label.setText(f"Batch ID: {batch_id}")
        QApplication.processEvents()

    ### 菜单栏功能组件

    def set_up_enter(self):
        """输入 MinerU API key"""

        dialog = MinerUAPIDialog(self)

        if dialog.exec_() == QDialog.Accepted:

            result = dialog.api_result.strip()

            if result:
                self.api_key = result
                self.api_label.setText("API Key: Ready")
                self.update_state_dialog("Done", "API key for MinerU has been set up.", self)

            else:
                self.update_state_dialog("Error", "No API key was entered!", self)
    
    def set_up_txt(self):
        """从 txt 文件中导入 MinerU API key"""

        txt_file_path, _ = QFileDialog.getOpenFileName(
            self, "Select a txt File for MinerU Configuration", "", "txt (*.txt)"
        )

        if txt_file_path:

            with open(txt_file_path, 'r', encoding='utf-8') as file:
                api_key = file.read().strip()

            if api_key:
                self.api_key = api_key
                self.api_label.setText("API Key: Ready")
                self.update_state_dialog("Done", "API key for MinerU has been set up.", self)
            
            else:
                self.update_state_dialog("Error", "No API key in the txt file!", self)
    
    def select_folders(self):
        """确定导入/导出文件夹的路径"""
            
        dialog = MinerUFolderDialog(self)
            
        if dialog.exec_() == QDialog.Accepted:

            result = dialog.folder_result

            if result['pdf'] and result['md'] and result['txt']:
                self.pdf_folder_path = result['pdf']
                self.md_folder_path = result['md']
                self.txt_folder_path = result['txt']
                self.folder_label.setText(f"Folder Paths: Ready")
                self.update_state_dialog("Done", "Folders for uploading and downloading have been selected.", self)

            else:
                self.update_state_dialog(
                    "Error", "Some of the folder(s) for uploading and downloading were not selected!", self
                )
    
    def running_mineru(self):
        """运行解析任务"""

        # 逐项检查配置与目录存在性，给出明确提示
        missing = []
        if not self.api_key:
            missing.append("API Key")
        if not self.pdf_folder_path:
            missing.append("PDF Folder")
        if not self.md_folder_path:
            missing.append("MD Folder")
        if not self.txt_folder_path:
            missing.append("Output Folder")
        not_found = []
        if self.pdf_folder_path and not path.exists(self.pdf_folder_path):
            not_found.append(f"PDF: {self.pdf_folder_path}")
        if self.md_folder_path and not path.exists(self.md_folder_path):
            not_found.append(f"MD: {self.md_folder_path}")
        if self.txt_folder_path and not path.exists(self.txt_folder_path):
            # 输出目录可自动创建
            try:
                path_check(self.txt_folder_path)
            except Exception:
                not_found.append(f"OUT: {self.txt_folder_path}")
        if missing or not_found:
            msg = []
            if missing:
                msg.append("Missing: " + ", ".join(missing))
            if not_found:
                msg.append("Not Found: " + ", ".join(not_found))
            msg.append("提示：可在项目根目录创建 .env（参考 .env.example），或通过菜单 Set up/Select Folders 配置。")
            self.update_state_dialog("Error", "\n".join(msg), self)
            return

        self.stacked_widget.setCurrentIndex(1)

        self.mineru_worker = MinerUWorker(
            self,
            self.api_key, self.pdf_folder_path, self.md_folder_path, self.txt_folder_path,
        )

        self.mineru_worker.id_text.connect(self.update_id)
        self.mineru_worker.update_text.connect(self.update_running_text)
        self.mineru_worker.error_signal.connect(self.on_mineru_error)
        self.mineru_worker.finished_signal.connect(self.on_mineru_finished)
    
        self.mineru_worker.start()
    
    def on_mineru_finished(self, result_data):
        """MinerU 任务完成后的操作"""

        self.log_json = result_data["log_json"]
        self.update_state_dialog("Done", "All processes have been completed successfully.", self)
    
    def on_mineru_error(self, error_message):
        """MinerU 任务出错时的操作"""

        self.update_state_dialog("Error", error_message, self)
    
    def clear_page(self):
        """清除 MinerU 运行状态消息"""

        self.running_text.clear()

    def show_about(self):
        """显示关于 DocNerd 的信息"""

        about_html_path = "about.html"
        dialog = HTMLDialog("About DocNerd", about_html_path, self)
        dialog.exec_()
 

if __name__ == '__main__':
    
    app = QApplication(argv)
    
    app.setStyle('Fusion')

    window = MinerUMainWindow()
    window.show()

    exit(app.exec_())
