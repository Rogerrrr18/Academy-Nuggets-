from PyQt5.QtGui import QFont


def choose_font(type):
    """生成固定样式的字体属性"""

    font, size = 'Microsoft YaHei UI', 10

    if type == 'label':
        return QFont(font, size, QFont.Bold)
    
    elif type == 'h1':
        return QFont(font, int(size * 2.4), QFont.Bold)
    
    elif type == 'h2':
        return QFont(font, int(size * 1.8), QFont.Bold)
    
    elif type == 'h3':
        return QFont(font, int(size * 1.2), QFont.Bold)
    
    else:
        return QFont(font, size)


def choose_style(type):
    """返回固定的风格描述"""

    if type == "green button":
        return """
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #43A047;
            }
            QPushButton:pressed {
                background-color: #388E3C;
            }
        """
    
    elif type == "blue button":
        return """
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
        """
    
    elif type == "ok button":
        return """
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
        """

    elif type == "cancel button":
        return """
            QPushButton {
                background-color: #f1f1f1;
                color: #333;
                border: 1px solid #ccc;
                padding: 8px 16px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #e1e1e1;
            }
            QPushButton:pressed {
                background-color: #d1d1d1;
            }
        """
    
    elif type == "label":
        return """
           QLabel {
                color: #2c3e50;
                padding: 5px;
                background-color: transparent;
                border: none;
            }
        """
    
    elif type == "big label":
        return """
           QLabel {
                color: #2c3e50;
                padding: 20px;
                background-color: transparent;
                border: none;
            }
        """
    
    elif type == "grey mid label":
        return """
            QLabel {
                color: #7f8c8d;
                padding: 10px;
                background-color: transparent;
                border: none;
            }
        """
    
    elif type == "state label":
        return """
            QLabel {
                color: #333;
                padding: 10px;
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 5px;
                margin-right: 10px;
            }
        """
    
    elif type == "main window":
        return """
            QMainWindow {
                background-color: #f0f0f0;
            }
            QMenuBar {
                background-color: #e0e0e0;
                border-bottom: 1px solid #d0d0d0;
                padding: 5px;
            }
            QMenuBar::item {
                padding: 8px 16px;
                margin: 2px;
            }
            QMenuBar::item:selected {
                background-color: #d0d0d0;
            }
        """
    
    elif type == "widget":
        return """
            QWidget {
                background-color: #f8f9fa;
                border: 2px solid #dee2e6;
                border-radius: 15px;
            }
        """

    elif type == "stacked widget":
        return """
            QStackedWidget {
                background-color: white;
                border: 1px solid #dee2e6;
                border-radius: 5px;
                margin: 10px;
            }
        """

    elif type == "text edit":
        return """
            QTextEdit {
                border: 1px solid #dee2e6;
                border-radius: 5px;
                padding: 10px;
                background-color: white;
                font-family: 'Microsoft YaHei UI', monospace;
            }
            QTextEdit:focus {
                border-color: #0078d4;
            }
        """
    
    elif type == "small text edit":
        return """
            QTextEdit {
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 5px;
                background-color: white;
            }
            QTextEdit:focus {
                border-color: #0078d4;
            }
        """
    
    elif type == "line edit":
        return """
            QLineEdit {
                border: 1px solid #dee2e6;
                border-radius: 5px;
                padding: 10px;
                background-color: white;
                font-family: 'Microsoft YaHei UI', monospace;
            }
            QLineEdit:focus {
                border-color: #0078d4;
            }
        """
    
    elif type == "web view":
        return """
            QWebEngineView {
                border: 1px solid #dee2e6;
                border-radius: 5px;
                background-color: #f8f9fa;
            }
        """
    
    elif type == "separator":
        return """
            background-color: #dee2e6;
            margin: 10px 0;
        """

    else:
        return "ERROR"