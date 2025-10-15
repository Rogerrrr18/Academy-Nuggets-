from os import path

from PyQt5.QtWidgets import QVBoxLayout, QLabel, QDialog, QTextEdit
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtWebEngineWidgets import QWebEngineView

# 可选依赖：my_htmls（缺失时兜底）
try:
    from my_htmls import error_txt_html  # type: ignore
except Exception:
    def error_txt_html(abs_path: str) -> str:
        return f"""
        <html><head><meta charset='utf-8'><title>Missing HTML</title></head>
        <body style='font-family: Microsoft YaHei UI, sans-serif;'>
            <h2>无法加载指定的 HTML 文件</h2>
            <p>路径：{abs_path}</p>
            <p>提示：my_htmls.py 未提供 error_txt_html，已使用内置兜底。</p>
        </body></html>
        """
from my_styles import choose_font


class HTMLDialog(QDialog):
    """用于弹出显示 html 内容的对话框"""

    def __init__(
            self, title, html_file_path,
            parent=None,
    ):
        """初始化对话框 -> 加载本地 html 文件 -> 让对话框在父对话框中央显示""" 
        
        super().__init__(parent)

        self.setWindowTitle(title)
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        
        self.resize(1800, 1000)
        
        layout = QVBoxLayout(self)
        self.web_view = QWebEngineView()
        layout.addWidget(self.web_view)
        
        self.load_html_file(html_file_path)
        self.center_dialog()
    
    def load_html_file(self, html_file_path):
        """加载本地HTML文件"""

        ab_path = path.abspath(html_file_path)

        if path.exists(html_file_path):
            file_url = QUrl.fromLocalFile(ab_path)
            self.web_view.load(file_url)
        else:
            self.web_view.setHtml(error_txt_html(ab_path))
    
    def center_dialog(self):
        """让对话框在父对话框中央显示"""

        if self.parent():
            parent_geometry = self.parent().geometry()
            x = parent_geometry.x() + (parent_geometry.width() - self.width()) // 2
            y = parent_geometry.y() + (parent_geometry.height() - self.height()) // 2
            self.move(x, y)


class StateDialog(QDialog):
    """用于弹出显示状态信息的对话框"""

    def __init__(
            self, state, prompt,
            parent=None
    ):
        """初始化对话框 -> 让对话框在父窗口中央显示"""
        
        super().__init__(parent)

        self.setWindowTitle(state)
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        
        self.resize(800, 400)
        
        layout = QVBoxLayout(self)
        
        type_label = QLabel(f"Status:")
        type_label.setFont(choose_font('label'))
        layout.addWidget(type_label)

        state_prompt = QTextEdit()
        state_prompt.setFont(choose_font('text'))
        state_prompt.setText(prompt)
        state_prompt.setReadOnly(True)
        layout.addWidget(state_prompt)
        
        self.center_dialog()
    
    def center_dialog(self):
        """让对话框在父窗口中央显示"""

        if self.parent():
            parent_geometry = self.parent().geometry()
            x = parent_geometry.x() + (parent_geometry.width() - self.width()) // 2
            y = parent_geometry.y() + (parent_geometry.height() - self.height()) // 2
            self.move(x, y)
