"""Settings dialog — all user-toggleable features in one place."""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QComboBox,
    QPushButton, QGroupBox, QFrame, QLineEdit, QMessageBox,
)
from PyQt6.QtCore import Qt
from config import get_setting, set_setting, DICTIONARY_PATH, STT_MODELS
from core.recorder import list_input_devices
import os
import subprocess


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SFlow — Ajustes")
        self.setMinimumWidth(460)

        root = QVBoxLayout()
        root.setSpacing(12)

        # --- Modelo de transcripción ---
        backend_group = QGroupBox("Modelo de transcripción")
        bl = QVBoxLayout()
        self.model_combo = QComboBox()
        for m in STT_MODELS:
            self.model_combo.addItem(m["label"], m["id"])
        current = get_setting("stt_model", "whisper-turbo-local")
        idx = max(0, self.model_combo.findData(current))
        self.model_combo.setCurrentIndex(idx)
        bl.addWidget(self.model_combo)
        hint = QLabel(
            "Local = offline, privado, gratis (Apple Silicon). Whisper Turbo = mejor\n"
            "precisión y usa tu diccionario. Parakeet = más rápido. Groq = nube."
        )
        hint.setStyleSheet("color: gray; font-size: 11px;")
        bl.addWidget(hint)

        # Selector de micrófono / dispositivo de entrada
        bl.addSpacing(6)
        bl.addWidget(QLabel("Micrófono / entrada de audio:"))
        self.mic_combo = QComboBox()
        self.mic_combo.addItem("Predeterminado del sistema", "")
        for d in list_input_devices():
            self.mic_combo.addItem(d["name"], d["name"])
        cur_mic = get_setting("input_device", "") or ""
        self.mic_combo.setCurrentIndex(max(0, self.mic_combo.findData(cur_mic)))
        bl.addWidget(self.mic_combo)
        mic_hint = QLabel("Aplica en el próximo dictado. Si el dispositivo se desconecta, usa el predeterminado.")
        mic_hint.setStyleSheet("color: gray; font-size: 11px;")
        bl.addWidget(mic_hint)

        backend_group.setLayout(bl)
        root.addWidget(backend_group)

        # --- AI post-processing ---
        ai_group = QGroupBox("Procesamiento con LLM")
        al = QVBoxLayout()
        al.addWidget(QLabel("Auto Cleanup (limpieza con LLM):"))
        self.cleanup_combo = QComboBox()
        self.cleanup_combo.addItem("None · sin limpieza (verbatim)", "none")
        self.cleanup_combo.addItem("Light · muletillas + puntuación", "light")
        self.cleanup_combo.addItem("Medium · claridad + concisión", "medium")
        _lvl = get_setting("auto_cleanup_level", "none")
        self.cleanup_combo.setCurrentIndex(max(0, self.cleanup_combo.findData(_lvl)))
        al.addWidget(self.cleanup_combo)

        prov_row = QHBoxLayout()
        prov_row.addWidget(QLabel("Proveedor de limpieza:"))
        self.provider_combo = QComboBox()
        self.provider_combo.addItem("Groq · Llama (nube)", "groq")
        self.provider_combo.addItem("OpenRouter · GLM (nube)", "openrouter")
        cur_prov = get_setting("llm_cleanup_provider", "groq")
        self.provider_combo.setCurrentIndex(max(0, self.provider_combo.findData(cur_prov)))
        prov_row.addWidget(self.provider_combo)
        al.addLayout(prov_row)

        prov_hint = QLabel(
            "OpenRouter (GLM) requiere OPENROUTER_API_KEY en el .env. Si falla o no hay\n"
            "key, se pega la transcripción cruda (nunca bloquea)."
        )
        prov_hint.setStyleSheet("color: gray; font-size: 11px;")
        al.addWidget(prov_hint)

        self.cb_context = QCheckBox("Adaptar tono según la app activa (Slack casual, Gmail formal, código, etc.)")
        self.cb_context.setChecked(get_setting("context_aware_tone", True))
        al.addWidget(self.cb_context)

        self.cb_commands = QCheckBox("Comandos de voz (\"nueva línea\", \"punto y aparte\", etc.)")
        self.cb_commands.setChecked(get_setting("smart_commands_enabled", True))
        al.addWidget(self.cb_commands)

        self.cb_dict = QCheckBox("Usar diccionario personal como vocabulario")
        self.cb_dict.setChecked(get_setting("personal_dictionary_enabled", True))
        al.addWidget(self.cb_dict)

        dict_row = QHBoxLayout()
        dict_row.addWidget(QLabel(f"Archivo: {DICTIONARY_PATH}"))
        edit_btn = QPushButton("Editar")
        edit_btn.clicked.connect(self._edit_dictionary)
        dict_row.addWidget(edit_btn)
        al.addLayout(dict_row)
        ai_group.setLayout(al)
        root.addWidget(ai_group)

        # --- UX ---
        ux_group = QGroupBox("UX")
        ul = QVBoxLayout()
        self.cb_glass = QCheckBox("Liquid Glass en la pill (macOS 26+)")
        self.cb_glass.setChecked(get_setting("liquid_glass_enabled", True))
        ul.addWidget(self.cb_glass)

        self.cb_stream = QCheckBox("Paste en streaming (efecto typing word-by-word)")
        self.cb_stream.setChecked(get_setting("streaming_paste_enabled", False))
        ul.addWidget(self.cb_stream)

        self.cb_command = QCheckBox("Command Mode (Ctrl+Shift hold → transforma selección con voz)")
        self.cb_command.setChecked(get_setting("command_mode_enabled", True))
        ul.addWidget(self.cb_command)
        ux_group.setLayout(ul)
        root.addWidget(ux_group)

        # --- Hotkeys ---
        hk_group = QGroupBox("Hotkey de mouse (opcional)")
        hl = QVBoxLayout()
        self.mouse_combo = QComboBox()
        self.mouse_combo.addItem("Ninguno", "")
        self.mouse_combo.addItem("Click medio (rueda)", "middle")
        self.mouse_combo.addItem("Botón lateral 1 (Mouse4)", "x1")
        self.mouse_combo.addItem("Botón lateral 2 (Mouse5)", "x2")
        cur_mb = get_setting("mouse_button_hotkey") or ""
        idx = max(0, self.mouse_combo.findData(cur_mb))
        self.mouse_combo.setCurrentIndex(idx)
        hl.addWidget(self.mouse_combo)
        hk_group.setLayout(hl)
        root.addWidget(hk_group)

        # --- Save ---
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(line)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        save = QPushButton("Guardar")
        save.setDefault(True)
        save.clicked.connect(self._save)
        btn_row.addWidget(save)
        root.addLayout(btn_row)

        self.setLayout(root)

    def _edit_dictionary(self):
        os.makedirs(os.path.dirname(DICTIONARY_PATH), exist_ok=True)
        if not os.path.exists(DICTIONARY_PATH):
            from core.dictionary import _ensure_file
            _ensure_file()
        subprocess.run(["open", "-a", "TextEdit", DICTIONARY_PATH], capture_output=True)

    def _save(self):
        set_setting("stt_model", self.model_combo.currentData())
        set_setting("input_device", self.mic_combo.currentData())
        set_setting("auto_cleanup_level", self.cleanup_combo.currentData())
        set_setting("llm_cleanup_provider", self.provider_combo.currentData())
        set_setting("context_aware_tone", self.cb_context.isChecked())
        set_setting("smart_commands_enabled", self.cb_commands.isChecked())
        set_setting("personal_dictionary_enabled", self.cb_dict.isChecked())
        set_setting("liquid_glass_enabled", self.cb_glass.isChecked())
        set_setting("streaming_paste_enabled", self.cb_stream.isChecked())
        set_setting("command_mode_enabled", self.cb_command.isChecked())
        mb = self.mouse_combo.currentData()
        set_setting("mouse_button_hotkey", mb if mb else None)

        QMessageBox.information(
            self, "Guardado",
            "Ajustes guardados. Algunos cambios (hotkey de mouse, Liquid Glass) requieren reiniciar SFlow.",
        )
        self.accept()
