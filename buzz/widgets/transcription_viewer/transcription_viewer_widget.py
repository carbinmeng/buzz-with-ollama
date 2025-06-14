import logging
from typing import Optional
from uuid import UUID

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QShowEvent
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtSql import QSqlRecord
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QToolButton,
    QLabel,
    QMessageBox,
    QInputDialog,
    QDialogButtonBox,
)

import srt
from srt_equalizer import srt_equalizer

from buzz.locale import _
from buzz.db.entity.transcription import Transcription
from buzz.db.service.transcription_service import TranscriptionService
from buzz.paths import file_path_as_title
from buzz.settings.shortcuts import Shortcuts
from buzz.settings.settings import Settings
from buzz.store.keyring_store import get_password, Key
from buzz.widgets.audio_player import AudioPlayer
from buzz.widgets.icon import (
    FileDownloadIcon,
    TranslateIcon,
    ResizeIcon,
)
from buzz.translator import Translator
from buzz.widgets.text_display_box import TextDisplayBox
from buzz.widgets.toolbar import ToolBar
from buzz.transcriber.transcriber import TranscriptionOptions, Segment
from buzz.widgets.transcriber.advanced_settings_dialog import AdvancedSettingsDialog
from buzz.widgets.transcription_viewer.export_transcription_menu import (
    ExportTranscriptionMenu,
)
from buzz.widgets.preferences_dialog.models.file_transcription_preferences import (
    FileTranscriptionPreferences,
)
from buzz.widgets.transcription_viewer.transcription_segments_editor_widget import (
    TranscriptionSegmentsEditorWidget,
)
from buzz.widgets.transcription_viewer.transcription_view_mode_tool_button import (
    TranscriptionViewModeToolButton,
    ViewMode
)
from buzz.assets import get_translation_provider

class OkEnabledInputDialog(QInputDialog):
    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        button_box = self.findChild(QDialogButtonBox)
        if button_box:
            ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
            if ok_button:
                ok_button.setEnabled(True)


class TranscriptionViewerWidget(QWidget):
    resize_button_clicked = pyqtSignal()
    rerun_triggered = pyqtSignal(tuple)
    transcription: Transcription
    settings = Settings()

    def __init__(
        self,
        transcription: Transcription,
        transcription_service: TranscriptionService,
        shortcuts: Shortcuts,
        parent: Optional["QWidget"] = None,
        flags: Qt.WindowType = Qt.WindowType.Widget,
    ) -> None:
        super().__init__(parent, flags)
        self.transcription = transcription
        self.transcription_service = transcription_service

        self.setMinimumWidth(800)
        self.setMinimumHeight(500)

        self.setWindowTitle(file_path_as_title(transcription.file))

        self.translation_thread = None
        self.translator = None
        self.view_mode = ViewMode.TIMESTAMPS

        self.openai_access_token = get_password(Key.OPENAI_API_KEY)

        preferences = self.load_preferences()

        (
            self.transcription_options,
            self.file_transcription_options,
        ) = preferences.to_transcription_options(
            openai_access_token=self.openai_access_token,
        )

        self.transcription_options_dialog = AdvancedSettingsDialog(
            transcription_options=self.transcription_options, parent=self
        )
        self.transcription_options_dialog.transcription_options_changed.connect(
            self.on_transcription_options_changed
        )

        self.translator = Translator(
            self.transcription_options,
            self.transcription_options_dialog,
        )

        self.translation_thread = QThread()
        self.translator.moveToThread(self.translation_thread)

        self.translation_thread.started.connect(self.translator.start)

        self.translation_thread.start()

        self.table_widget = TranscriptionSegmentsEditorWidget(
            transcription_id=UUID(hex=transcription.id),
            translator=self.translator,

            parent=self
        )
        self.table_widget.segment_selected.connect(self.on_segment_selected)

        self.text_display_box = TextDisplayBox(self)
        font = QFont(self.text_display_box.font().family(), 14)
        self.text_display_box.setFont(font)

        self.audio_player = AudioPlayer(file_path=transcription.file)
        self.audio_player.position_ms_changed.connect(
            self.on_audio_player_position_ms_changed
        )

        self.current_segment_label = QLabel("", self)
        self.current_segment_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.current_segment_label.setContentsMargins(0, 0, 0, 10)
        self.current_segment_label.setWordWrap(True)

        font_metrics = self.current_segment_label.fontMetrics()
        max_height = font_metrics.lineSpacing() * 3
        self.current_segment_label.setMaximumHeight(max_height)

        layout = QVBoxLayout(self)

        toolbar = ToolBar(self)

        view_mode_tool_button = TranscriptionViewModeToolButton(shortcuts, self)
        view_mode_tool_button.view_mode_changed.connect(self.on_view_mode_changed)
        toolbar.addWidget(view_mode_tool_button)

        export_tool_button = QToolButton()
        export_tool_button.setText(_("Export"))
        export_tool_button.setIcon(FileDownloadIcon(self))
        export_tool_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )

        export_transcription_menu = ExportTranscriptionMenu(
            transcription, transcription_service, self
        )
        export_tool_button.setMenu(export_transcription_menu)
        export_tool_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        toolbar.addWidget(export_tool_button)

        translate_button = QToolButton()
        translate_button.setText(_("Translate"))
        translate_button.setIcon(TranslateIcon(self))
        translate_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        translate_button.clicked.connect(self.on_translate_button_clicked)

        toolbar.addWidget(translate_button)

        resize_button = QToolButton()
        resize_button.setText(_("Resize"))
        resize_button.setObjectName("resize_button")
        resize_button.setIcon(ResizeIcon(self))
        resize_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        resize_button.clicked.connect(self.on_resize_button_clicked)

        toolbar.addWidget(resize_button)

        # Add Rerun button
        rerun_button = QToolButton()
        rerun_button.setText(_("Rerun"))
        rerun_button.setObjectName("rerun_button")
        rerun_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        rerun_button.clicked.connect(self.on_rerun_button_clicked)

        toolbar.addWidget(rerun_button)

        layout.setMenuBar(toolbar)

        layout.addWidget(self.table_widget)
        layout.addWidget(self.text_display_box)
        layout.addWidget(self.audio_player)
        layout.addWidget(self.current_segment_label)

        self.setLayout(layout)

        self.reset_view()

    def reset_view(self):
        if self.view_mode == ViewMode.TIMESTAMPS:
            self.text_display_box.hide()
            self.table_widget.show()
        elif self.view_mode == ViewMode.TEXT:
            segments = self.transcription_service.get_transcription_segments(
                transcription_id=self.transcription.id_as_uuid
            )

            combined_text = ""
            previous_end_time = None

            for segment in segments:
                if previous_end_time is not None and (segment.start_time - previous_end_time) >= 2000:
                    combined_text += "\n\n"
                combined_text += segment.text.strip() + " "
                previous_end_time = segment.end_time

            self.text_display_box.setPlainText(combined_text.strip())
            self.text_display_box.show()
            self.table_widget.hide()
        else: # ViewMode.TRANSLATION
            # TODO add check for if translation exists
            segments = self.transcription_service.get_transcription_segments(
                transcription_id=self.transcription.id_as_uuid
            )
            self.text_display_box.setPlainText(
                " ".join(segment.translation.strip() for segment in segments)
            )
            self.text_display_box.show()
            self.table_widget.hide()

    def on_view_mode_changed(self, view_mode: ViewMode) -> None:
        self.view_mode = view_mode
        self.reset_view()

    def on_segment_selected(self, segment: QSqlRecord):
        if (
            self.audio_player.media_player.playbackState()
            == QMediaPlayer.PlaybackState.PlayingState
        ):
            self.audio_player.set_range(
                (segment.value("start_time"), segment.value("end_time"))
            )

    def on_audio_player_position_ms_changed(self, position_ms: int) -> None:
        segments = self.table_widget.segments()
        current_segment = next(
            (
                segment
                for segment in segments
                if segment.value("start_time")
                <= position_ms
                < segment.value("end_time")
            ),
            None,
        )
        if current_segment is not None:
            self.current_segment_label.setText(current_segment.value("text"))

    def load_preferences(self):
        self.settings.settings.beginGroup("file_transcriber")
        preferences = FileTranscriptionPreferences.load(settings=self.settings.settings)
        self.settings.settings.endGroup()
        return preferences

    def open_advanced_settings(self):
        self.transcription_options_dialog.show()

    def on_transcription_options_changed(
            self, transcription_options: TranscriptionOptions
    ):
        self.transcription_options = transcription_options

    def on_translate_button_clicked(self):
        if len(self.openai_access_token) == 0:
            QMessageBox.information(
                self,
                _("API Key Required"),
                _("Please enter OpenAI API Key in preferences")
            )

            return


        translation_provider = get_translation_provider()

        if translation_provider == "OPENAI":
            if self.transcription_options.llm_model == "" or self.transcription_options.llm_prompt == "":
                self.transcription_options_dialog.show()
                return

        segments = self.table_widget.segments()
        logging.debug(f"on_translate_button_clicked: Enqueuing {len(segments)} segments for translation")
        for segment in segments:
            self.translator.enqueue(segment.value("text"), segment.value("id"))

    def on_resize_button_clicked(self):
        target_chars_dialog = OkEnabledInputDialog(self)
        target_chars_dialog.setOkButtonText(_("Ok"))
        target_chars_dialog.setCancelButtonText(_("Cancel"))
        target_chars_dialog.setWindowTitle(_("Desired subtitle length"))
        target_chars_dialog.setLabelText(_("Enter target characters per subtitle:"))
        target_chars_dialog.setIntValue(42)
        target_chars_dialog.setIntMaximum(100)
        target_chars_dialog.setIntMinimum(1)
        target_chars_dialog.setIntStep(1)
        target_chars_dialog.setInputMode(QInputDialog.InputMode.IntInput)

        if target_chars_dialog.exec() == QInputDialog.DialogCode.Accepted:
            target_chars = target_chars_dialog.intValue()
        else:
            return

        segments = self.table_widget.segments()
        subs = []
        for segment in segments:
            subtitle = srt.Subtitle(
                index=segment.value("id"),
                start=segment.value("start_time"),
                end=segment.value("end_time"),
                content=segment.value("text")
            )
            subs.append(subtitle)

        resized_subs = []
        last_index = 0

        # Limit each subtitle to a maximum character length, splitting into
        # multiple subtitle items if necessary.
        for sub in subs:
            new_subs = srt_equalizer.split_subtitle(
                sub=sub, target_chars=target_chars, start_from_index=last_index, method="punctuation")
            last_index = new_subs[-1].index
            resized_subs.extend(new_subs)

        segments = [
            Segment(
                round(sub.start),
                round(sub.end),
                sub.content
            )
            for sub in resized_subs
            if round(sub.start) != round(sub.end)
        ]

        self.transcription_service.replace_transcription_segments(
            UUID(hex=self.transcription.id),
            segments
        )

        self.table_widget.model().select()
        self.table_widget.init_row_height()
        
    # def on_resize_button_clicked(self):
    #     self.resize_button_clicked.emit()
        
    def on_rerun_button_clicked(self):
        # Get the model path from the transcription options
        model_path = self.transcription_options.model.get_local_model_path()
        
        # Create file transcription options with the file path from the current transcription
        self.file_transcription_options.file_paths = [self.transcription.file]
        self.file_transcription_options.url = None
        
        # Show a confirmation dialog with OK and Cancel buttons
        confirmation = QMessageBox.question(
            self,
            _("Rerun Transcription"),
            _("Do you want to rerun the transcription?"),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        
        # If the user confirmed, emit the signal and close the widget
        if confirmation == QMessageBox.StandardButton.Ok:
            # Emit the rerun_triggered signal with the same tuple format as FileTranscriberWidget.triggered
            self.rerun_triggered.emit(
                (self.transcription_options, self.file_transcription_options, model_path)
            )
            
            # # Show a confirmation message
            # QMessageBox.information(
            #     self,
            #     _("Rerun Transcription"),
            #     _("Transcription task has been added to the queue.")
            # )
            
            # Close the widget
            self.close()

    def closeEvent(self, event):
        self.hide()

        self.translator.stop()
        self.translation_thread.quit()
        self.translation_thread.wait()

        super().closeEvent(event)
