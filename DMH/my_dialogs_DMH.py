from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QDialog, QPushButton, QTextEdit, QFileDialog, QLineEdit
from PyQt5.QtCore import Qt

from my_styles import choose_font, choose_style


class MinerUAPIDialog(QDialog):
    """弹出填写 MinerU API key 内容的对话框"""

    def __init__(
            self,
            parent=None,
    ):
        """初始化对话框 -> 让对话框在父对话框中央显示"""
        
        super().__init__(parent)

        self.setWindowTitle("Set up MinerU Configuration")
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        
        self.resize(1200, 400)

        self.api_result = None
        
        layout = QVBoxLayout(self)

        mineru_label = QLabel("Enter your API key for MinerU:")
        mineru_label.setFont(choose_font('label'))
        layout.addWidget(mineru_label)

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Enter the API key here...")
        self.text_edit.setFont(choose_font('text'))
        self.text_edit.setStyleSheet(choose_style('small text edit'))
        layout.addWidget(self.text_edit)

        button_layout = QHBoxLayout()
        
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        ok_button.setFont(choose_font('label'))
        ok_button.setStyleSheet(choose_style('ok button'))
        button_layout.addWidget(ok_button)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        cancel_button.setFont(choose_font('label'))
        cancel_button.setStyleSheet(choose_style('cancel button'))
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        
        self.center_dialog()
    
    def center_dialog(self):
        """让对话框在父对话框中央显示"""

        if self.parent():
            parent_geometry = self.parent().geometry()
            x = parent_geometry.x() + (parent_geometry.width() - self.width()) // 2
            y = parent_geometry.y() + (parent_geometry.height() - self.height()) // 2
            self.move(x, y)
    
    def accept(self):
        """用户点击确定时获取其填写的 MinerU API key"""
        
        self.api_result = self.text_edit.toPlainText()  
        super().accept()


class MinerUFolderDialog(QDialog):
    """弹出选择 MinerU 导入/导出文件夹路径的对话框"""

    def __init__(
            self,
            parent=None,
    ):
        """初始化对话框 -> 创建导入/导出文件夹选择行 -> 创建按钮 -> 让对话框在父对话框中央显示"""
        
        super().__init__(parent)

        self.setWindowTitle("Select Folders")
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        
        self.resize(1600, 400)

        self.row_labels = ["pdf", "md", "txt"]
        self.folder_result = {}
        
        layout = QVBoxLayout(self)

        self.create_folder_rows(layout)
        self.create_buttons(layout)
        self.center_dialog()
    
    def create_folder_rows(self, main_layout):
        """创建导入/导出文件夹选择行"""
        
        self.folder_line_edits = []
        defaults = {
            "pdf": "7-杨皓然-高研院/paper",
            "md": "mineru_raw",
            "txt": "md_clean",
        }
        
        for i, label_text in enumerate(self.row_labels):

            row_layout = QHBoxLayout()
            
            label = QLabel(f"{label_text}: ")
            label.setFont(choose_font('label'))
            row_layout.addWidget(label)

            line_edit = QLineEdit()
            line_edit.setPlaceholderText(f"Select a folder...")
            line_edit.setFont(choose_font('text'))
            line_edit.setReadOnly(True)
            # 预填默认目录，便于快速开始
            if label_text in defaults:
                line_edit.setText(defaults[label_text])
            row_layout.addWidget(line_edit)
            
            browse_button = QPushButton("Browse")
            browse_button.setFont(choose_font('label'))
            browse_button.setStyleSheet(choose_style('blue button'))         
            browse_button.clicked.connect(lambda checked, idx=i: self.browse_folder(idx))
            row_layout.addWidget(browse_button)
            
            main_layout.addLayout(row_layout)
            
            self.folder_line_edits.append(line_edit)
    
    def browse_folder(self, row_index):
        """浏览文件夹"""

        line_edit = self.folder_line_edits[row_index]
        
        folder_path = QFileDialog.getExistingDirectory(
            self, "Select a Folder", "", QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        
        if folder_path:
            line_edit.setText(folder_path)
    
    def create_buttons(self, main_layout):
        """创建按钮"""

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        ok_button.setFont(choose_font('label'))
        ok_button.setStyleSheet(choose_style('ok button'))
        button_layout.addWidget(ok_button)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        cancel_button.setFont(choose_font('label'))
        cancel_button.setStyleSheet(choose_style('cancel button'))
        button_layout.addWidget(cancel_button)
        
        main_layout.addLayout(button_layout)
    
    def center_dialog(self):
        """让对话框在父对话框中央显示"""

        if self.parent():
            parent_geometry = self.parent().geometry()
            x = parent_geometry.x() + (parent_geometry.width() - self.width()) // 2
            y = parent_geometry.y() + (parent_geometry.height() - self.height()) // 2
            self.move(x, y)
    
    def accept(self):
        """用户点击确定时获取其选择的 MinerU 导入/导出文件夹"""

        for i, row_label in enumerate(self.row_labels):
            self.folder_result[row_label] = self.folder_line_edits[i].text()

        super().accept()
