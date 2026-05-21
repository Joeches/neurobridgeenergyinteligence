"""
Console handler with Windows encoding support for emoji characters
"""

import sys
import logging
import platform

class SafeConsoleHandler(logging.StreamHandler):
    """Console handler that safely handles emoji characters on Windows"""
    
    def __init__(self, stream=None):
        super().__init__(stream or sys.stdout)
        self._setup_encoding()
    
    def _setup_encoding(self):
        """Setup proper encoding for console output"""
        if platform.system() == 'Windows':
            try:
                # Try to set console to UTF-8
                import subprocess
                subprocess.run('chcp 65001', shell=True, capture_output=True)
            except:
                pass
    
    def emit(self, record):
        """Emit record with safe character handling"""
        try:
            msg = self.format(record)
            # Replace problematic emojis with ASCII equivalents on Windows
            if platform.system() == 'Windows':
                msg = self._safe_emoji_replace(msg)
            stream = self.stream
            stream.write(msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)
    
    def _safe_emoji_replace(self, msg: str) -> str:
        """Replace emojis with ASCII equivalents"""
        replacements = {
            '🚀': '[ROCKET]',
            '🔐': '[LOCK]',
            '✅': '[OK]',
            '❌': '[X]',
            '⚠️': '[WARN]',
            '📡': '[SIGNAL]',
            '🌍': '[EARTH]',
            '🛰️': '[SATELLITE]',
            '🔌': '[PLUG]',
            '🎯': '[TARGET]',
            '🧠': '[BRAIN]',
            '⚡': '[BOLT]',
            '💻': '[PC]',
            '📄': '[DOC]',
            '📊': '[CHART]',
            '📈': '[TREND]',
            '🔑': '[KEY]',
            '🔄': '[REFRESH]',
            '🎯': '[TARGET]',
            '📅': '[CAL]',
            '🔧': '[TOOL]',
            '📦': '[PACKAGE]',
            '🗺️': '[MAP]',
            '🛡️': '[SHIELD]',
            '🔒': '[LOCKED]',
            '🔓': '[UNLOCKED]',
            '⚙️': '[GEAR]',
            '📝': '[NOTE]',
            '🐢': '[SLOW]',
            '✅': '[OK]',
            '❌': '[X]',
            '⚠️': '[!]',
            '🔍': '[SEARCH]',
            '📡': '[ANTENNA]',
            '🌐': '[GLOBE]',
            '🏭': '[FACTORY]',
            '☀️': '[SUN]',
            '🌙': '[MOON]',
            '☁️': '[CLOUD]',
            '🌧️': '[RAIN]',
            '⚡': '[LIGHTNING]',
            '🔥': '[FIRE]',
            '💡': '[IDEA]',
            '📌': '[PIN]',
            '🔔': '[BELL]',
            '💾': '[SAVE]',
            '📁': '[FOLDER]',
            '📂': '[FOLDER]',
            '📤': '[UPLOAD]',
            '📥': '[DOWNLOAD]',
            '🔄': '[SYNC]',
            '⏰': '[TIME]',
            '⏱️': '[TIMER]',
            '🎉': '[CELEBRATE]',
            '🏆': '[TROPHY]',
            '⭐': '[STAR]',
            '💯': '[100]',
            '🔴': '[RED]',
            '🟢': '[GREEN]',
            '🟡': '[YELLOW]',
            '🔵': '[BLUE]',
            '🟣': '[PURPLE]',
            '⚫': '[BLACK]',
            '⚪': '[WHITE]',
            '🟤': '[BROWN]',
            '🔺': '[UP]',
            '🔻': '[DOWN]',
            '◀️': '[LEFT]',
            '▶️': '[RIGHT]',
            '▲': '[UP]',
            '▼': '[DOWN]',
            '◄': '[LEFT]',
            '►': '[RIGHT]',
        }
        
        for emoji, ascii_replacement in replacements.items():
            msg = msg.replace(emoji, ascii_replacement)
        
        return msg