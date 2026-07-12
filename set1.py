import os
import sys
import shutil
import subprocess
import configparser
import json
import time
import zipfile
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTreeView, QPushButton,
                            QVBoxLayout, QHBoxLayout, QWidget, QMessageBox,
                            QFileDialog, QLabel, QLineEdit, QDialog, QComboBox,
                            QTabWidget, QCheckBox, QSplitter, QFrame, QProgressBar,
                            QProgressDialog)
from PyQt5.QtCore import Qt, QDir, QModelIndex, QTimer, QSize, QThread, pyqtSignal
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QIcon
from smb.SMBConnection import SMBConnection

class GameLauncherConfig:
    def __init__(self, config_file="config.ini"):
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        
        # 기본 설정
        self.nas_url = "" # SMB는 URL 형식이 아닌 IP 주소 형식
        self.username = ""
        self.password = ""
        self.local_dir = "%userprofile%\desktop\새 폴더"
        self.nas_share = "TurtleIPXService" # SMB 공유 이름
        self.remote_dir = "tests" # 공유 내 경로
        self.game_execs = {} # 게임별 실행 파일 정보
        self.last_played = {} # 게임별 마지막 플레이 시간
        self.favorites = [] # 즐겨찾기 게임 목록
        self.auto_sync = False # 자동 동기화 설정
        self.profiles = {} # 다중 계정 프로필
        
        self.load_config()
    
    def load_config(self):
        if os.path.exists(self.config_file):
            self.config.read(self.config_file)
            
            if 'NAS' in self.config:
                self.nas_url = self.config['NAS'].get('url', '')
                self.username = self.config['NAS'].get('username', '')
                self.password = self.config['NAS'].get('password', '')
                self.nas_share = self.config['NAS'].get('share', 'homes')
                self.remote_dir = self.config['NAS'].get('remote_dir', '/jwh/Turtle_IE_ZIPFILES/done/')
            
            if 'LOCAL' in self.config:
                self.local_dir = self.config['LOCAL'].get('directory', '')
            
            if 'GAMES' in self.config:
                self.game_execs = json.loads(self.config['GAMES'].get('execs', '{}'))
                self.last_played = json.loads(self.config['GAMES'].get('last_played', '{}'))
                self.favorites = json.loads(self.config['GAMES'].get('favorites', '[]'))
            
            if 'SETTINGS' in self.config:
                self.auto_sync = self.config['SETTINGS'].getboolean('auto_sync', False)
            
            if 'PROFILES' in self.config:
                self.profiles = json.loads(self.config['PROFILES'].get('data', '{}'))
    
    def save_config(self):
        if 'NAS' not in self.config:
            self.config['NAS'] = {}
        self.config['NAS']['url'] = self.nas_url
        self.config['NAS']['username'] = self.username
        self.config['NAS']['password'] = self.password
        self.config['NAS']['share'] = self.nas_share
        self.config['NAS']['remote_dir'] = self.remote_dir
        
        if 'LOCAL' not in self.config:
            self.config['LOCAL'] = {}
        self.config['LOCAL']['directory'] = self.local_dir
        
        if 'GAMES' not in self.config:
            self.config['GAMES'] = {}
        self.config['GAMES']['execs'] = json.dumps(self.game_execs)
        self.config['GAMES']['last_played'] = json.dumps(self.last_played)
        self.config['GAMES']['favorites'] = json.dumps(self.favorites)
        
        if 'SETTINGS' not in self.config:
            self.config['SETTINGS'] = {}
        self.config['SETTINGS']['auto_sync'] = str(self.auto_sync)
        
        if 'PROFILES' not in self.config:
            self.config['PROFILES'] = {}
        self.config['PROFILES']['data'] = json.dumps(self.profiles)
        
        with open(self.config_file, 'w') as f:
            self.config.write(f)
    
    def set_game_exec(self, game_path, exec_path):
        self.game_execs[game_path] = exec_path
        self.save_config()
    
    def get_game_exec(self, game_path):
        return self.game_execs.get(game_path, "")
    
    def set_last_played(self, game_path, timestamp):
        self.last_played[game_path] = timestamp
        self.save_config()
    
    def get_last_played(self, game_path):
        return self.last_played.get(game_path, "")
    
    def add_to_favorites(self, game_path):
        if game_path not in self.favorites:
            self.favorites.append(game_path)
            self.save_config()
    
    def remove_from_favorites(self, game_path):
        if game_path in self.favorites:
            self.favorites.remove(game_path)
            self.save_config()
    
    def is_favorite(self, game_path):
        return game_path in self.favorites
    
    def get_favorites(self):
        return self.favorites
    
    def set_auto_sync(self, enabled):
        self.auto_sync = enabled
        self.save_config()
    
    def get_auto_sync(self):
        return self.auto_sync
    
    def get_played_games(self):
        return list(self.last_played.keys())
    
    def add_profile(self, name, url, username, password, share="homes", remote_dir="/jwh/Turtle_IE_ZIPFILES/done/"):
        self.profiles[name] = {
            "url": url,
            "username": username,
            "password": password,
            "share": share,
            "remote_dir": remote_dir
        }
        self.save_config()
    
    def get_profile(self, name):
        return self.profiles.get(name, None)
    
    def get_profile_names(self):
        return list(self.profiles.keys())
    
    def delete_profile(self, name):
        if name in self.profiles:
            del self.profiles[name]
            self.save_config()

# 다운로드 워커 클래스 추가
class DownloadWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, nas, remote_path, local_path):
        super().__init__()
        self.nas = nas
        self.remote_path = remote_path
        self.local_path = local_path
        self.total_size = 0
        self.downloaded_size = 0
        
    def run(self):
        try:
            success = self.nas.download_game(self.remote_path, self.local_path, self.update_progress)
            self.finished.emit(success, self.local_path)
        except Exception as e:
            print(f"다운로드 오류: {e}")
            self.finished.emit(False, str(e))
    
    def update_progress(self, current, total):
       if total > 0:
         percent = int((current / total) * 100)
         self.progress.emit(percent)
         # 반환값이 없도록 합니다


# 업로드 워커 클래스 추가
class UploadWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool)
    
    def __init__(self, nas, local_dir, remote_dir, original_files):
        super().__init__()
        self.nas = nas
        self.local_dir = local_dir
        self.remote_dir = remote_dir
        self.original_files = original_files
        
    def run(self):
        try:
            success = self.nas.upload_changes(self.local_dir, self.remote_dir, self.original_files, self.update_progress)
            self.finished.emit(success)
        except Exception as e:
            print(f"업로드 오류: {e}")
            self.finished.emit(False)
    
    def update_progress(self, current, total):
        if total > 0:
            percent = int((current / total) * 100)
            self.progress.emit(percent)

class NASConnector:
    def __init__(self, config):
        self.config = config
        self.client = None
        self.connect()
    
    def connect(self):
        try:
            # SMB 연결 설정
            self.client = SMBConnection(
                self.config.username,
                self.config.password,
                "MAINSERVER", # 로컬 컴퓨터 이름
                "TurtleNetNAS", # 원격 서버 이름
                use_ntlm_v2=True,
                is_direct_tcp=True
            )
            
            # NAS에 연결
            connected = self.client.connect(self.config.nas_url, 445) # SMB 연결코드
            if not connected:
                raise Exception("SMB 연결 실패")
        except Exception as e:
            print(f"SMB 연결 오류: {e}")
            raise
    
    def list_games(self, path=None):
        if path is None:
            path = self.config.remote_dir
        
        games = []
        try:
            # 경로의 시작 부분에서 슬래시 제거
            path = path.replace('\\', '/').strip('/')
            
            # SMB 공유에서 파일 목록 가져오기
            file_list = self.client.listPath(self.config.nas_share, path)
            
            for file_info in file_list:
                # . 및 .. 디렉토리 건너뛰기
                if file_info.filename in ['.', '..']:
                    continue
                
                file_path = f"{path}/{file_info.filename}" if path else file_info.filename
                
                if file_info.isDirectory:
                    # 디렉토리인 경우 재귀적으로 탐색
                    sub_games = self.list_games(file_path)
                    games.extend(sub_games)
                else:
                    # 파일인 경우 목록에 추가 (ZIP 파일만 필터링)
                    if file_info.filename.lower().endswith('.zip'):
                        games.append(f"/{file_path}")
                    else:
                        games.append(f"/{file_path}")
            
        except Exception as e:
            print(f"게임 목록 가져오기 오류: {e}")
        
        return games
    
    def is_dir(self, path):
        try:
            # 경로의 시작 부분에서 슬래시 제거
            # path = path.lstrip('/')
            
            # 부모 디렉토리와 파일명 분리
            parent_dir = os.path.dirname(path)
            filename = os.path.basename(path)
            
            # 빈 파일명인 경우 (루트 디렉토리)
            if not filename:
                return True
            
            # 부모 디렉토리의 파일 목록 가져오기
            file_list = self.client.listPath(self.config.nas_share, parent_dir if parent_dir else '/')
            
            # 해당 이름의 파일이 디렉토리인지 확인
            for file_info in file_list:
                if file_info.filename == filename:
                    return file_info.isDirectory
            
            return False
        except Exception as e:
            print(f"디렉토리 확인 오류: {e}")
            return False
    
    def download_game(self, remote_path, local_path, progress_callback=None):
        try:
            # 로컬 디렉토리 생성
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # 경로의 시작 부분에서 슬래시 제거
            clean_remote_path = remote_path.lstrip('/')
            
            # ZIP 파일 경로 설정
            zip_filename = os.path.basename(remote_path)
            if not zip_filename.lower().endswith('.zip'):
                zip_filename += '.zip'
            
            temp_zip_path = os.path.join(os.path.dirname(local_path), zip_filename)
            
            # 파일 크기 확인
            try:
                file_info = self.client.getAttributes(self.config.nas_share, clean_remote_path)
                total_size = file_info.file_size
            except Exception as e:
                print(f"파일 크기 확인 오류: {e}")
                total_size = 0
            
            # 다운로드 진행
            downloaded_size = 0
            
            with open(temp_zip_path, 'wb') as local_file:
                if remote_path.lower().endswith('.zip'):
                    # 이미 ZIP 파일인 경우 직접 다운로드
                    def callback(data):
                        try:
                            nonlocal downloaded_size
                            downloaded_size += len(data)
                            local_file.write(data)
                            if progress_callback is not None and callable(progress_callback) and total_size > 0:
                                progress_callback(downloaded_size, total_size)
                        except Exception as e:
                            print(f"콜백 함수 오류: {e}")
                        return len(data)
                    
                    self.client.retrieveFile(self.config.nas_share, clean_remote_path, local_file)
                else:
                    # 디렉토리인 경우 ZIP으로 압축하여 다운로드
                    # 임시 디렉토리 생성
                    temp_dir = os.path.join(os.path.dirname(local_path), "temp_download")
                    os.makedirs(temp_dir, exist_ok=True)
                    
                     #디렉토리 내용 다운로드
                    self._download_directory(clean_remote_path, temp_dir, progress_callback)
                    
                    # ZIP 파일로 압축
                    self._compress_directory(temp_dir, temp_zip_path, progress_callback)
                    
                    # 임시 디렉토리 삭제
                    shutil.rmtree(temp_dir)
            
            # ZIP 파일 압축 해제
            try:
               with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
               # 압축 해제할 디렉토리 생성
                 folder_path = temp_zip_path.replace('.zip', '')
                 zip_ref.extractall(folder_path)
                 print(folder_path)
                # total_files = len(zip_ref.infolist())
                # for i, file in enumerate(zip_ref.infolist()):
                    #  zip_ref.extract(file, local_path)
                    #  if progress_callback is not None and callable(progress_callback):
                       #    try:
                       #         progress_callback(i + 1, total_files)
                       #    except Exception as e:
                       #          print(f"진행 상황 업데이트 오류: {e}")
            except Exception as e:
                   print(f"ZIP 파일 압축 해제 오류: {e}")
                   return False
            
            # 임시 ZIP 파일 삭제
            os.remove(temp_zip_path)
            
            return True
        except Exception as e:
            print(f"게임 다운로드 오류: {e}")
            return False
    
    def _download_directory(self, remote_dir, local_dir, progress_callback=None):
        try:
            os.makedirs(local_dir, exist_ok=True)
            
            # 디렉토리 내용 가져오기
            file_list = self.client.listPath(self.config.nas_share, remote_dir)
            
            total_files = len([f for f in file_list if f.filename not in ['.', '..']])
            current_file = 0
            
            for file_info in file_list:
                if file_info.filename in ['.', '..']:
                    continue
                
                remote_path = f"{remote_dir}/{file_info.filename}"
                local_path = os.path.join(local_dir, file_info.filename)
                
                if file_info.isDirectory:
                    # 디렉토리인 경우 재귀적으로 다운로드
                    self._download_directory(remote_path, local_path, progress_callback)
                else:
                    # 파일인 경우 다운로드
                    with open(local_path, 'wb') as local_file:
                        self.client.retrieveFile(self.config.nas_share, remote_path, local_file)
                
                current_file += 1
                if progress_callback:
                    progress_callback(current_file, total_files)
            
            return True
        except Exception as e:
            print(f"디렉토리 다운로드 오류: {e}")
            return False
    
    def _compress_directory(self, directory, zip_path, progress_callback=None):
        try:
            # 디렉토리 내 모든 파일 목록 가져오기
            file_paths = []
            for root, dirs, files in os.walk(directory):
                for file in files:
                    file_paths.append(os.path.join(root, file))
            
            # 총 파일 수
            total_files = len(file_paths)
            
            # ZIP 파일 생성
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for i, file_path in enumerate(file_paths):
                    # 상대 경로 계산
                    rel_path = os.path.relpath(file_path, directory)
                    # 파일 추가
                    zipf.write(file_path, rel_path)
                    # 진행 상황 업데이트
                    if progress_callback:
                        progress_callback(i + 1, total_files)
            
            return True
        except Exception as e:
            print(f"디렉토리 압축 오류: {e}")
            return False
    
def upload_changes(self, local_dir, remote_dir, original_files, progress_callback=None):
     try:
        # 원래 ZIP 파일명 추출
        zip_filename = os.path.basename(remote_dir)
        if not zip_filename.lower().endswith('.zip'):
            zip_filename += '.zip'

        # 임시 ZIP 파일 경로 설정
        temp_dir = os.path.dirname(local_dir)
        temp_zip_path = os.path.join(temp_dir, zip_filename)

        # 전체 디렉토리를 ZIP으로 압축
        with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            total_files = sum([len(files) for _, _, files in os.walk(local_dir)])
            processed_files = 0
            for root, _, files in os.walk(local_dir):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, local_dir)
                    zipf.write(full_path, rel_path)
                    processed_files += 1
                    if progress_callback:
                        progress_callback(processed_files, total_files)

        # 원격 경로 설정 (파일명 포함)
        remote_zip_path = remote_dir if remote_dir.lower().endswith('.zip') else remote_dir + '.zip'

        # 파일 업로드 (덮어쓰기)
        with open(temp_zip_path, 'rb') as file_obj:
            self.client.storeFile(self.config.nas_share, remote_zip_path, file_obj)

        # 임시 ZIP 파일 삭제
        os.remove(temp_zip_path)

        return True
     except Exception as e:
        print(f"변경사항 업로드 오류: {e}")
        return False
#메인 UI 코드
class GameLauncherUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = GameLauncherConfig()
        self.nas = None
        self.original_files = {}
        self.current_game_path = ""
        self.game_start_time = None
        self.log_file = "game_launcher.log"
        self.download_worker = None
        self.upload_worker = None
        
        self.init_ui()
        
        if self.config.nas_url and self.config.username and self.config.password:
            self.connect_to_nas()
        
        # 자동 동기화 타이머 설정
        self.sync_timer = QTimer()
        self.sync_timer.timeout.connect(self.sync_all_games)
        if self.config.get_auto_sync():
            self.sync_timer.start(3600000) # 1시간마다 동기화

    def init_ui(self):
        self.setWindowTitle("Synology NAS Game Launcher")
        self.setGeometry(100, 100, 1000, 700)
        
        # 메인 위젯 및 레이아웃
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        
        # 상단 도구 모음
        top_layout = QHBoxLayout()
        
        # NAS 연결 설정 버튼
        self.settings_btn = QPushButton("NAS 설정")
        self.settings_btn.clicked.connect(self.show_settings)
        top_layout.addWidget(self.settings_btn)
        
        # 프로필 선택 콤보박스
        profile_layout = QHBoxLayout()
        profile_layout.addWidget(QLabel("프로필:"))
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(self.config.get_profile_names())
        self.profile_combo.currentIndexChanged.connect(self.change_profile)
        profile_layout.addWidget(self.profile_combo)
        
        self.add_profile_btn = QPushButton("프로필 관리")
        self.add_profile_btn.clicked.connect(self.manage_profiles)
        profile_layout.addWidget(self.add_profile_btn)
        
        top_layout.addLayout(profile_layout)
        
        # 자동 동기화 체크박스
        self.auto_sync_check = QCheckBox("자동 동기화")
        self.auto_sync_check.setChecked(self.config.get_auto_sync())
        self.auto_sync_check.stateChanged.connect(self.toggle_auto_sync)
        top_layout.addWidget(self.auto_sync_check)
        
        # 검색 상자
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("게임 검색...")
        self.search_box.textChanged.connect(self.filter_games)
        top_layout.addWidget(self.search_box)
        
        main_layout.addLayout(top_layout)
        
        # 메인 콘텐츠 영역 (스플리터 사용)
        splitter = QSplitter(Qt.Horizontal)
        
        # 탭 위젯 (모든 게임 / 즐겨찾기)
        self.tabs = QTabWidget()
        
        # 모든 게임 탭
        self.all_games_tab = QWidget()
        all_games_layout = QVBoxLayout()
        
        # 게임 목록 트리뷰
        self.game_tree = QTreeView()
        self.game_model = QStandardItemModel()
        self.game_model.setHorizontalHeaderLabels(["게임 목록"])
        self.game_tree.setModel(self.game_model)
        self.game_tree.clicked.connect(self.game_selected)
        self.game_tree.doubleClicked.connect(self.download_and_run)
        all_games_layout.addWidget(self.game_tree)
        
        self.all_games_tab.setLayout(all_games_layout)
        
        # 즐겨찾기 탭
        self.favorites_tab = QWidget()
        favorites_layout = QVBoxLayout()
        
        self.favorites_tree = QTreeView()
        self.favorites_model = QStandardItemModel()
        self.favorites_model.setHorizontalHeaderLabels(["즐겨찾기 게임"])
        self.favorites_tree.setModel(self.favorites_model)
        self.favorites_tree.clicked.connect(self.favorite_selected)
        self.favorites_tree.doubleClicked.connect(self.download_and_run_favorite)
        favorites_layout.addWidget(self.favorites_tree)
        
        self.favorites_tab.setLayout(favorites_layout)
        
        # 탭 추가
        self.tabs.addTab(self.all_games_tab, "모든 게임")
        self.tabs.addTab(self.favorites_tab, "즐겨찾기")
        
        splitter.addWidget(self.tabs)
        
        # 게임 정보 패널
        self.info_panel = QFrame()
        self.info_panel.setFrameShape(QFrame.StyledPanel)
        info_layout = QVBoxLayout()
        
        info_title = QLabel("게임 정보")
        info_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        info_layout.addWidget(info_title)
        
        self.game_title = QLabel("")
        self.game_path = QLabel("")
        self.last_played = QLabel("")
        
        info_layout.addWidget(self.game_title)
        info_layout.addWidget(self.game_path)
        info_layout.addWidget(self.last_played)
        
        # 즐겨찾기 버튼
        self.favorite_btn = QPushButton("즐겨찾기에 추가")
        self.favorite_btn.clicked.connect(self.toggle_favorite)
        info_layout.addWidget(self.favorite_btn)
        
        # 실행 버튼
        self.run_btn = QPushButton("다운로드 및 실행")
        self.run_btn.clicked.connect(self.download_and_run)
        info_layout.addWidget(self.run_btn)
        
        # 새로고침 버튼
        self.refresh_btn = QPushButton("목록 새로고침")
        self.refresh_btn.clicked.connect(self.refresh_game_list)
        info_layout.addWidget(self.refresh_btn)
        
        info_layout.addStretch()
        self.info_panel.setLayout(info_layout)
        
        splitter.addWidget(self.info_panel)
        
        # 스플리터 비율 설정
        splitter.setSizes([700, 300])
        
        main_layout.addWidget(splitter)
        
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)
    
    def select_executable(self, game_dir):
   # """게임 디렉토리에서 실행 파일을 선택합니다."""
      try:
        # 실행 파일 목록 찾기
        executables = []
        for root, dirs, files in os.walk(game_dir):
            for file in files:
                if file.lower().endswith('.exe'):
                    rel_path = os.path.relpath(os.path.join(root, file), game_dir)
                    executables.append(rel_path)
        
        if not executables:
            QMessageBox.warning(self, "경고", "게임 디렉토리에서 실행 파일(.exe)을 찾을 수 없습니다.")
            return ""
        
        # 하나만 있으면 자동 선택
        if len(executables) == 1:
            return executables[0]
        
        # 여러 개 있으면 사용자가 선택
        dialog = QDialog(self)
        dialog.setWindowTitle("실행 파일 선택")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        layout.addWidget(QLabel("실행할 파일을 선택하세요:"))
        
        list_widget = QComboBox()
        list_widget.addItems(executables)
        layout.addWidget(list_widget)
        
        button_layout = QHBoxLayout()
        ok_button = QPushButton("선택")
        ok_button.clicked.connect(dialog.accept)
        button_layout.addWidget(ok_button)
        
        cancel_button = QPushButton("취소")
        cancel_button.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        dialog.setLayout(layout)
        
        if dialog.exec_() == QDialog.Accepted:
            return list_widget.currentText()
        
        return ""
      except Exception as e:
        QMessageBox.critical(self, "오류", f"실행 파일 선택 중 오류가 발생했습니다: {str(e)}")
        self.log_action("ERROR", f"Executable selection error: {str(e)}")
        return ""

    def show_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("NAS 설정")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        
        # NAS URL
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("NAS IP 주소:"))
        url_edit = QLineEdit(self.config.nas_url)
        url_layout.addWidget(url_edit)
        layout.addLayout(url_layout)
        
        # 사용자 이름
        username_layout = QHBoxLayout()
        username_layout.addWidget(QLabel("사용자 이름:"))
        username_edit = QLineEdit(self.config.username)
        username_layout.addWidget(username_edit)
        layout.addLayout(username_layout)
        
        # 비밀번호
        password_layout = QHBoxLayout()
        password_layout.addWidget(QLabel("비밀번호:"))
        password_edit = QLineEdit(self.config.password)
        password_edit.setEchoMode(QLineEdit.Password)
        password_layout.addWidget(password_edit)
        layout.addLayout(password_layout)
        
       # SMB 공유 이름
        share_layout = QHBoxLayout()
        share_layout.addWidget(QLabel("SMB 공유 이름:"))
        share_edit = QLineEdit(self.config.nas_share)
        share_layout.addWidget(share_edit)
        share_help = QLabel("예: homes (\\\\서버주소\\공유이름 형식의 '공유이름' 부분)")
        share_help.setStyleSheet("color: gray; font-size: 10px;")
        share_layout.addWidget(share_help)
        layout.addLayout(share_layout)

        
        # 원격 디렉토리
        remote_dir_layout = QHBoxLayout()
        remote_dir_layout.addWidget(QLabel("원격 디렉토리:"))
        remote_dir_edit = QLineEdit(self.config.remote_dir)
        remote_dir_layout.addWidget(remote_dir_edit)
        layout.addLayout(remote_dir_layout)
        
        # 로컬 디렉토리
        local_dir_layout = QHBoxLayout()
        local_dir_layout.addWidget(QLabel("로컬 디렉토리:"))
        local_dir_edit = QLineEdit(self.config.local_dir)
        local_dir_layout.addWidget(local_dir_edit)
        browse_btn = QPushButton("찾아보기")
        browse_btn.clicked.connect(lambda: self.browse_directory(local_dir_edit))
        local_dir_layout.addWidget(browse_btn)
        layout.addLayout(local_dir_layout)
        
        # 버튼
        button_layout = QHBoxLayout()
        save_btn = QPushButton("저장")
        save_btn.clicked.connect(lambda: self.save_settings(
            url_edit.text(), 
            username_edit.text(), 
            password_edit.text(),
            share_edit.text(),
            remote_dir_edit.text(),
            local_dir_edit.text(),
            dialog
        ))
        button_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        dialog.exec_()
    
    def browse_directory(self, line_edit):
        directory = QFileDialog.getExistingDirectory(self, "로컬 디렉토리 선택")
        if directory:
            line_edit.setText(directory)
    
    def save_settings(self, url, username, password, share, remote_dir, local_dir, dialog):
        self.config.nas_url = url
        self.config.username = username
        self.config.password = password
        self.config.nas_share = share
        self.config.remote_dir = remote_dir
        self.config.local_dir = local_dir
        self.config.save_config()
        
        dialog.accept()
        self.connect_to_nas()
    
    def connect_to_nas(self):
        try:
            self.nas = NASConnector(self.config)
            self.refresh_game_list()
            self.log_action("CONNECT", f"Connected to NAS: {self.config.nas_url}")
        except Exception as e:
            QMessageBox.critical(self, "연결 오류", f"NAS 연결 중 오류가 발생했습니다: {str(e)}")
            self.log_action("ERROR", f"Connection error: {str(e)}")
    
    def manage_profiles(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("프로필 관리")
        dialog.setMinimumWidth(500)
        
        layout = QVBoxLayout()
        
        # 프로필 목록
        layout.addWidget(QLabel("저장된 프로필:"))
        profile_combo = QComboBox()
        profile_combo.addItems(self.config.get_profile_names())
        layout.addWidget(profile_combo)
        
        # 프로필 정보 입력
        form_layout = QVBoxLayout()
        
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("프로필 이름:"))
        name_edit = QLineEdit()
        name_layout.addWidget(name_edit)
        form_layout.addLayout(name_layout)
        
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("NAS IP 주소:"))
        url_edit = QLineEdit()
        url_layout.addWidget(url_edit)
        form_layout.addLayout(url_layout)
        
        username_layout = QHBoxLayout()
        username_layout.addWidget(QLabel("사용자 이름:"))
        username_edit = QLineEdit()
        username_layout.addWidget(username_edit)
        form_layout.addLayout(username_layout)
        
        password_layout = QHBoxLayout()
        password_layout.addWidget(QLabel("비밀번호:"))
        password_edit = QLineEdit()
        password_edit.setEchoMode(QLineEdit.Password)
        password_layout.addWidget(password_edit)
        form_layout.addLayout(password_layout)
        
        share_layout = QHBoxLayout()
        share_layout.addWidget(QLabel("SMB 공유 이름:"))
        share_edit = QLineEdit("homes")
        share_layout.addWidget(share_edit)
        form_layout.addLayout(share_layout)
        
        remote_dir_layout = QHBoxLayout()
        remote_dir_layout.addWidget(QLabel("원격 디렉토리:"))
        remote_dir_edit = QLineEdit("/jwh/Turtle_IE_ZIPFILES/done/")
        remote_dir_layout.addWidget(remote_dir_edit)
        form_layout.addLayout(remote_dir_layout)
        
        layout.addLayout(form_layout)
        
        # 프로필 선택 시 정보 표시
        def load_profile():
            name = profile_combo.currentText()
            if name:
                profile = self.config.get_profile(name)
                if profile:
                    name_edit.setText(name)
                    url_edit.setText(profile["url"])
                    username_edit.setText(profile["username"])
                    password_edit.setText(profile["password"])
                    share_edit.setText(profile.get("share", "homes"))
                    remote_dir_edit.setText(profile.get("remote_dir", "/jwh/Turtle_IE_ZIPFILES/done/"))
        
        profile_combo.currentIndexChanged.connect(load_profile)
        load_profile()  # 초기 로드
        
        # 버튼 레이아웃
        button_layout = QHBoxLayout()
        
        add_btn = QPushButton("추가/수정")
        add_btn.clicked.connect(lambda: self.add_profile(
            name_edit.text(),
            url_edit.text(),
            username_edit.text(),
            password_edit.text(),
            share_edit.text(),
            remote_dir_edit.text(),
            profile_combo
        ))
        button_layout.addWidget(add_btn)
        
        delete_btn = QPushButton("삭제")
        delete_btn.clicked.connect(lambda: self.delete_profile(profile_combo.currentText(), profile_combo))
        button_layout.addWidget(delete_btn)
        
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        dialog.exec_()
    
    def add_profile(self, name, url, username, password, share, remote_dir, combo):
        if not name:
            QMessageBox.warning(self, "경고", "프로필 이름을 입력하세요.")
            return
        
        if not url or not username or not password:
            QMessageBox.warning(self, "경고", "모든 필드를 입력하세요.")
            return
        
        self.config.add_profile(name, url, username, password, share, remote_dir)
        
        # 콤보박스 업데이트
        current_items = [combo.itemText(i) for i in range(combo.count())]
        if name not in current_items:
            combo.addItem(name)
        
        # 메인 UI의 프로필 콤보박스 업데이트
        self.profile_combo.clear()
        self.profile_combo.addItems(self.config.get_profile_names())
        
        QMessageBox.information(self, "성공", f"프로필 '{name}'이(가) 저장되었습니다.")
    
    def delete_profile(self, name, combo):
        if not name:
            return
        
        reply = QMessageBox.question(self, "확인", 
                                    f"프로필 '{name}'을(를) 삭제하시겠습니까?",
                                    QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.config.delete_profile(name)
            
            # 콤보박스에서 제거
            index = combo.findText(name)
            if index >= 0:
                combo.removeItem(index)
            
            # 메인 UI의 프로필 콤보박스 업데이트
            self.profile_combo.clear()
            self.profile_combo.addItems(self.config.get_profile_names())
            
            QMessageBox.information(self, "성공", f"프로필 '{name}'이(가) 삭제되었습니다.")
    
    def change_profile(self, index):
        if index < 0:
            return
        
        name = self.profile_combo.itemText(index)
        if not name:
            return
        
        profile = self.config.get_profile(name)
        if profile:
            self.config.nas_url = profile["url"]
            self.config.username = profile["username"]
            self.config.password = profile["password"]
            self.config.nas_share = profile.get("share", "homes")
            self.config.remote_dir = profile.get("remote_dir", "/jwh/Turtle_IE_ZIPFILES/done/")
            self.config.save_config()
            
            self.connect_to_nas()
    
    def toggle_auto_sync(self, state):
        enabled = state == Qt.Checked
        self.config.set_auto_sync(enabled)
        
        if enabled:
            self.sync_timer.start(3600000)  # 1시간마다 동기화
            self.log_action("SETTINGS", "Auto sync enabled")
        else:
            self.sync_timer.stop()
            self.log_action("SETTINGS", "Auto sync disabled")
    
    def sync_all_games(self):
        if not self.nas or not self.config.local_dir:
            return
        
        self.log_action("SYNC", "Starting automatic sync")
        
        for game_path in self.config.get_played_games():
            local_path = os.path.join(self.config.local_dir, os.path.basename(game_path))
            if os.path.exists(local_path):
                try:
                    self.nas.upload_changes(local_path, game_path, {})
                    self.log_action("SYNC", f"Auto-synced game: {game_path}")
                except Exception as e:
                    self.log_action("ERROR", f"Auto-sync failed for {game_path}: {str(e)}")
    
    def refresh_game_list(self):
        if not self.nas:
            QMessageBox.warning(self, "경고", "NAS에 연결되어 있지 않습니다.")
            return
        
        self.game_model.clear()
        self.game_model.setHorizontalHeaderLabels(["게임 목록"])
        
        root_item = self.game_model.invisibleRootItem()
        
        # 게임 목록 가져오기
        games = self.nas.list_games()
        
        # 트리 구조로 변환
        folders = {}
        
        for game_path in games:
            path_parts = game_path.split('/')
            current_path = ""
            parent_item = root_item
            
            for i, part in enumerate(path_parts):
                if not part:  # 빈 문자열 건너뛰기
                    continue
                
                current_path = current_path + "/" + part if current_path else "/" + part
                
                if current_path not in folders:
                    item = QStandardItem(part)
                    item.setData(current_path, Qt.UserRole)
                    
                    # 즐겨찾기 표시
                    if self.config.is_favorite(current_path):
                        item.setIcon(QIcon("star.png"))  # 별표 아이콘 (파일 필요)
                    
                    parent_item.appendRow(item)
                    folders[current_path] = item
                
                parent_item = folders[current_path]
        
        self.game_tree.expandAll()
        
        # 즐겨찾기 목록 업데이트
        self.update_favorites_list()
        
        self.log_action("REFRESH", "Game list refreshed")
    
    def update_favorites_list(self):
        self.favorites_model.clear()
        self.favorites_model.setHorizontalHeaderLabels(["즐겨찾기 게임"])
        
        root_item = self.favorites_model.invisibleRootItem()
        
        for game_path in self.config.get_favorites():
            name = os.path.basename(game_path)
            item = QStandardItem(name)
            item.setData(game_path, Qt.UserRole)
            item.setIcon(QIcon("star.png"))  # 별표 아이콘
            root_item.appendRow(item)
    
    def game_selected(self, index):
        item = self.game_model.itemFromIndex(index)
        if item:
            game_path = item.data(Qt.UserRole)
            self.current_game_path = game_path
            self.update_game_info(game_path)
    
    def favorite_selected(self, index):
        item = self.favorites_model.itemFromIndex(index)
        if item:
            game_path = item.data(Qt.UserRole)
            self.current_game_path = game_path
            self.update_game_info(game_path)
    
    def update_game_info(self, game_path):
        self.game_title.setText(f"제목: {os.path.basename(game_path)}")
        self.game_path.setText(f"경로: {game_path}")
        
        # 마지막 플레이 시간
        last_played = self.config.get_last_played(game_path)
        if last_played:
            self.last_played.setText(f"마지막 플레이: {last_played}")
        else:
            self.last_played.setText("아직 플레이하지 않음")
        # 즐겨찾기 버튼 상태 업데이트
        if self.config.is_favorite(game_path):
            self.favorite_btn.setText("즐겨찾기에서 제거")
        else:
            self.favorite_btn.setText("즐겨찾기에 추가")
    
    def toggle_favorite(self):
        if not self.current_game_path:
            return
        
        if self.config.is_favorite(self.current_game_path):
            self.config.remove_from_favorites(self.current_game_path)
            self.favorite_btn.setText("즐겨찾기에 추가")
            self.log_action("FAVORITE", f"Removed from favorites: {self.current_game_path}")
        else:
            self.config.add_to_favorites(self.current_game_path)
            self.favorite_btn.setText("즐겨찾기에서 제거")
            self.log_action("FAVORITE", f"Added to favorites: {self.current_game_path}")
        
        # 게임 목록과 즐겨찾기 목록 업데이트
        self.refresh_game_list()
    
    def download_and_run_favorite(self, index):
        item = self.favorites_model.itemFromIndex(index)
        if item:
            game_path = item.data(Qt.UserRole)
            self.current_game_path = game_path
            self.download_and_run()
    
    def filter_games(self, text):
        search_text = text.lower()
        
        # 모든 게임 목록 필터링
        for i in range(self.game_model.rowCount()):
            item = self.game_model.item(i)
            self.filter_tree_item(item, search_text)
        
        # 즐겨찾기 목록 필터링
        for i in range(self.favorites_model.rowCount()):
            item = self.favorites_model.item(i)
            if search_text in item.text().lower():
                self.favorites_tree.setRowHidden(i, QModelIndex(), False)
            else:
                self.favorites_tree.setRowHidden(i, QModelIndex(), True)
    
    def filter_tree_item(self, item, text):
        if not item:
            return False
        
        visible = False
        if text in item.text().lower():
            visible = True
        
        # 자식 아이템 확인
        for row in range(item.rowCount()):
            child = item.child(row)
            child_visible = self.filter_tree_item(child, text)
            visible = visible or child_visible
        
        self.game_tree.setRowHidden(item.row(), item.parent().index() if item.parent() else QModelIndex(), not visible)
        return visible

    def download_and_run(self):
        if not self.current_game_path:
            QMessageBox.warning(self, "경고", "게임을 선택해주세요.")
            return
        
        if not self.config.local_dir:
            QMessageBox.warning(self, "경고", "로컬 디렉토리를 설정해주세요.")
            return
        
        # 게임 다운로드
        local_game_path = os.path.normpath(os.path.join(self.config.local_dir, os.path.basename(self.current_game_path)))
        
        if os.path.exists(local_game_path):
            reply = QMessageBox.question(self, "확인",
              f"{os.path.basename(self.current_game_path)}가 이미 존재합니다. 덮어쓰시겠습니까?",
              QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                return
        
        # 다운로드 진행 대화상자 생성
        progress_dialog = QProgressDialog("게임 다운로드 중...", "취소", 0, 100, self)
        progress_dialog.setWindowTitle("다운로드")
        progress_dialog.setWindowModality(Qt.WindowModal)
        progress_dialog.setAutoClose(True)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)
        progress_dialog.show()
        
        # 다운로드 워커 생성 및 시작
        self.download_worker = DownloadWorker(self.nas, self.current_game_path, local_game_path)
        self.download_worker.progress.connect(progress_dialog.setValue)
        self.download_worker.finished.connect(lambda success, path: self.handle_download_finished(success, path, progress_dialog))
        
        self.log_action("DOWNLOAD", f"Downloading game: {self.current_game_path}")
        self.download_worker.start()
    
    def handle_download_finished(self, success, path, progress_dialog):
        progress_dialog.setValue(100)
        
        if not success:
            QMessageBox.critical(self, "오류", f"게임 다운로드 중 오류가 발생했습니다: {path}")
            self.log_action("ERROR", f"Download failed: {self.current_game_path}")
            return
        
        local_game_path = path
        
        # 원본 파일 상태 저장
        self.original_files = {}
        for root, dirs, files in os.walk(local_game_path):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, local_game_path)
                self.original_files[rel_path] = os.path.getmtime(full_path)
        
        # 실행 파일 설정 또는 선택
        exec_path = self.config.get_game_exec(self.current_game_path)
        if not exec_path:
            exec_path = self.select_executable(local_game_path.replace('.zip', ''))
            if exec_path:
                self.config.set_game_exec(local_game_path.replace('.zip', ''), exec_path)
        
        if not exec_path:
            QMessageBox.warning(self, "경고", "실행 파일을 선택하지 않았습니다.")
            return
        
        # 게임 실행
        full_exec_path = os.path.join(local_game_path.replace('.zip', ''), exec_path)
        try:
            # 게임 시작 시간 기록
            self.game_start_time = time.time()
            
            # 마지막 플레이 시간 업데이트
            self.config.set_last_played(self.current_game_path, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            
            # 로그 기록
            self.log_action("LAUNCH", f"Launched game: {self.current_game_path}")
            
            # 게임 실행
            subprocess.Popen(full_exec_path, cwd=os.path.dirname(full_exec_path))
            
            # 게임 종료 후 처리를 위한 대화상자
            QMessageBox.information(self, "안내",
                "게임이 실행되었습니다. 게임을 종료한 후 이 창을 닫으면 변경사항을 업로드합니다.")
            
            # 게임 종료 시간 계산
            play_duration = 0
            if self.game_start_time:
                play_duration = int((time.time() - self.game_start_time) / 60)
            self.log_action("EXIT", f"Game exited after {play_duration} minutes: {self.current_game_path}")
            
            # 변경사항 업로드
            self.handle_game_exit(local_game_path)
            
        except Exception as e:
            QMessageBox.critical(self, "오류", f"게임 실행 중 오류가 발생했습니다: {str(e)}")
            self.log_action("ERROR", f"Launch error: {str(e)}")
    
    def handle_game_exit(self, local_game_path):
        # 게임 종료 후 처리
        reply = QMessageBox.question(self, "업로드",
            "변경된 파일을 NAS에 업로드하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            # 업로드 진행 대화상자 생성
            progress_dialog = QProgressDialog("변경사항 업로드 중...", "취소", 0, 100, self)
            progress_dialog.setWindowTitle("업로드")
            progress_dialog.setWindowModality(Qt.WindowModal)
            progress_dialog.setAutoClose(True)
            progress_dialog.setMinimumDuration(0)
            progress_dialog.setValue(0)
            progress_dialog.show()
            
            # 업로드 워커 생성 및 시작
            self.upload_worker = UploadWorker(self.nas, local_game_path, self.current_game_path, self.original_files)
            self.upload_worker.progress.connect(progress_dialog.setValue)
            self.upload_worker.finished.connect(lambda success: self.handle_upload_finished(success, progress_dialog, local_game_path))
            
            self.log_action("UPLOAD", f"Uploading changes for: {self.current_game_path}")
            self.upload_worker.start()
    
        if reply == QMessageBox.No:
          reply = QMessageBox.question(self, "삭제",
              "다운로드한 게임 파일을 삭제하시겠습니까?",
              QMessageBox.Yes | QMessageBox.No)
        
          if reply == QMessageBox.Yes:
             try:
               if os.path.isfile(local_game_path.replace('.zip', '')):
                   os.remove(local_game_path.replace('.zip', ''))
               else:
                     shutil.rmtree(local_game_path.replace('.zip', ''))
                     QMessageBox.information(self, "완료", "게임 파일이 삭제되었습니다.")
                     self.log_action("DELETE", f"Deleted local files: {local_game_path.replace('.zip', '')}")
             except Exception as e:
                  QMessageBox.critical(self, "오류", f"파일 삭제 중 오류가 발생했습니다: {str(e)}")
                  self.log_action("ERROR", f"Delete error: {str(e)}")

    def handle_upload_finished(self, success, progress_dialog, local_game_path):
        progress_dialog.setValue(100)
        
        if success:
            QMessageBox.information(self, "완료", "변경사항이 성공적으로 업로드되었습니다.")
            self.log_action("UPLOAD", "Upload successful")
        else:
            QMessageBox.critical(self, "오류", "변경사항 업로드 중 오류가 발생했습니다.")
            self.log_action("ERROR", "Upload failed")
        
        # 로컬 파일 삭제 여부 확인
        reply = QMessageBox.question(self, "삭제",
            "다운로드한 게임 파일을 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
           try:
             if os.path.isfile(local_game_path):
                 os.remove(local_game_path)
             else:
                   shutil.rmtree(local_game_path)
                   QMessageBox.information(self, "완료", "게임 파일이 삭제되었습니다.")
                   self.log_action("DELETE", f"Deleted local files: {local_game_path}")
           except Exception as e:
                QMessageBox.critical(self, "오류", f"파일 삭제 중 오류가 발생했습니다: {str(e)}")
                self.log_action("ERROR", f"Delete error: {str(e)}")

    def log_action(self, action, message):
        """프로그램 동작 로그를 기록합니다."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} - [{action}] {message}\n")
        except Exception as e:
            print(f"로그 기록 오류: {e}")


def apply_stylesheet(app):
    app.setStyleSheet("""
    QMainWindow {
        background-color: #f0f0f0;
    }
    
    QTreeView {
        background-color: white;
        border: 1px solid #cccccc;
        border-radius: 4px;
    }
    
    QPushButton {
        background-color: #2980b9;
        color: white;
        border: none;
        padding: 5px 10px;
        border-radius: 3px;
    }
    
    QPushButton:hover {
        background-color: #3498db;
    }
    
    QLineEdit {
        padding: 5px;
        border: 1px solid #cccccc;
        border-radius: 3px;
    }
    
    QLabel {
        color: #333333;
    }
    
    QFrame {
        background-color: white;
        border-radius: 5px;
    }
    
    QProgressBar {
        border: 1px solid #cccccc;
        border-radius: 3px;
        text-align: center;
    }
    
    QProgressBar::chunk {
        background-color: #2980b9;
    }
    """)

def main():
    app = QApplication(sys.argv)
    apply_stylesheet(app)
    window = GameLauncherUI()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()