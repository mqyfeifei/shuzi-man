import unittest
from unittest.mock import AsyncMock, patch
import backend.pipeline as pipeline
from backend.config import settings
from backend.db import init_db, rows
from backend.services import ServiceError, _extract_tts_audio
from backend.voices import DEFAULT_VOICE_ID, VOICE_IDS, VOICES
from backend.pipeline import SOURCE_FILES, available_sources
from backend.catalog import generate_video_catalog
from backend.seed import SCENIC_QA
from backend.final_videos import clean_question_for_filename, organized_filename

class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): init_db()
    def test_seeded_three_spots_and_qa(self):
        spots=rows('SELECT id,name FROM scenic_spots ORDER BY id')
        self.assertEqual([x['name'] for x in spots],['灵山景区','敦煌','西湖'])
        for spot in spots:
            count=rows('SELECT COUNT(*) count FROM qa_items WHERE scenic_spot_id=?',(spot['id'],))[0]['count']
            expected={'灵山景区':70,'敦煌':40,'西湖':40}[spot['name']]
            self.assertEqual(count,expected)
    def test_questions_are_unique(self):
        for items in SCENIC_QA.values():
            questions=[question for question,_ in items]
            self.assertEqual(len(questions),len(set(questions)))
    def test_tts_audio_parser(self):
        self.assertEqual(_extract_tts_audio({'code':3000,'data':'YWJjZGVm'}),b'abcdef')
    def test_tts_error(self):
        with self.assertRaises(ServiceError):_extract_tts_audio({'code':55000000,'message':'mismatch'})
    def test_voice_catalog(self):
        self.assertIn(DEFAULT_VOICE_ID,VOICE_IDS)
        self.assertEqual(len(VOICES),20)
        self.assertEqual(VOICE_IDS, {
            'zh_female_tianmeixiaoyuan_uranus_bigtts','zh_female_vv_uranus_bigtts',
            'zh_female_gaolengyujie_uranus_bigtts','BV001_streaming','BV002_streaming',
            'BV113_streaming','BV033_streaming','BV102_streaming','BV503_streaming',
            'BV504_streaming','BV005_streaming','BV705_streaming','BV700_streaming',
            'BV034_streaming','BV701_streaming','BV007_streaming','BV051_streaming',
            'BV524_streaming','BV056_streaming','BV522_streaming'})
    def test_persistence_directories(self):
        for folder in (settings.audio_dir,settings.video_dir,settings.material_dir,settings.final_video_dir):self.assertTrue(folder.is_dir())
    def test_final_video_filename(self):
        self.assertEqual(clean_question_for_filename('灵山胜境在哪里？'),'灵山胜境在哪里')
        self.assertEqual(organized_filename(1,'灵山景区','灵山胜境在哪里？'),'001-灵山-灵山胜境在哪里.mp4')
        self.assertEqual(organized_filename(1,'灵山景区','灵山胜境在哪里？',2),'001-灵山-灵山胜境在哪里2.mp4')
        self.assertEqual(organized_filename(2,'敦煌','莫高窟为什么重要？'),'002-敦煌-莫高窟为什么重要.mp4')
    def test_pipeline_schema_and_source_mapping(self):
        self.assertEqual(SOURCE_FILES['灵山景区'],'灵山.mp4')
        self.assertEqual(SOURCE_FILES['敦煌'],'敦煌.mp4')
        self.assertEqual(SOURCE_FILES['西湖'],'西湖.mp4')
        self.assertTrue(available_sources()['灵山景区']['available'])
        tables={x['name'] for x in rows("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({'pipeline_jobs','pipeline_items'} <= tables)
    def test_video_catalog_export(self):
        path,count=generate_video_catalog('http://127.0.0.1:8000/')
        html=path.read_text(encoding='utf-8')
        expected=rows("SELECT COUNT(*) count FROM video_assets WHERE status='completed' AND relative_path IS NOT NULL")[0]['count']
        self.assertEqual(count,expected)
        self.assertIn('数字人视频问答索引',html)
        self.assertIn('charset="utf-8"',html)


class PipelineQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_queue_drains_jobs_in_order(self):
        with patch.object(pipeline, 'next_queued_job_id', side_effect=[12, 13, None]), \
             patch.object(pipeline, 'run', new_callable=AsyncMock) as run:
            await pipeline._drain_queue()
        self.assertEqual([call.args[0] for call in run.await_args_list], [12, 13])

if __name__=='__main__':unittest.main()
