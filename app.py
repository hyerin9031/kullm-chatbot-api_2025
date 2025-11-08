import requests
import json
from typing import List, Dict
from datetime import datetime
import random
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
from flask import session
import os

app = Flask(__name__)
CORS(app)

# KULLM 관련 라이브러리
try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    TRANSFORMERS_AVAILABLE = True
    print("✅ torch와 transformers 사용 가능")
except ImportError as e:
    TRANSFORMERS_AVAILABLE = False
    print(f"⚠️ transformers 또는 torch 없음: {e}")

# ============================
# 1. 온통청년 API 연동
# ============================

class YouthPolicyAPI:
    def __init__(self, api_key: str):
        self.api_url = "https://www.youthcenter.go.kr/go/ythip/getPlcy"
        self.api_key = api_key

    def get_policies(self, page_num: int = 1, page_size: int = 100) -> Dict:
        """청년 정책 데이터 가져오기"""
        params = {
            "apiKeyNm": self.api_key,
            "pageNum": page_num,
            "pageSize": page_size,
            "rtnType": "json"
        }

        try:
            response = requests.get(self.api_url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                return None
        except Exception as e:
            print(f"온통청년 API 요청 오류: {e}")
            return None

    def search_policies(self,
                       age: int = None,
                       region: str = None,
                       category: str = None,
                       keyword: str = None,
                       max_results: int = 3,
                       all_ages: bool = False) -> List[Dict]:
        """조건에 맞는 정책 검색"""
        data = self.get_policies(page_size=100)

        if not data or 'result' not in data:
            return []

        policies = data['result'].get('youthPolicyList', [])
        filtered_policies = []

        for policy in policies:
            # 나이 필터링
            if age or all_ages:
                try:
                    min_age = int(policy.get('sprtTrgtMinAge', 0))
                    max_age = int(policy.get('sprtTrgtMaxAge', 999))
                    
                    # 비정상적인 나이 값 제거
                    if min_age < 0 or min_age > 120 or max_age < 0 or max_age > 120:
                        continue
                    
                    # 전연령 검색
                    if all_ages:
                        age_range = max_age - min_age
                        if age_range < 50:
                            continue
                    elif age:
                        if not (min_age <= age <= max_age):
                            continue
                except:
                    pass

            # 지역 필터링
            if region:
                inst_name = policy.get('rgtrInstCdNm', '')
                region_match = False
                
                region_mapping = {
                    '서울': ['서울'],
                    '부산': ['부산'],
                    '대구': ['대구'],
                    '인천': ['인천'],
                    '광주': ['광주'],
                    '대전': ['대전'],
                    '울산': ['울산'],
                    '세종': ['세종'],
                    '경기': ['경기'],
                    '강원': ['강원'],
                    '충북': ['충청북도', '충북'],
                    '충남': ['충청남도', '충남'],
                    '충청': ['충청북도', '충북', '충청남도', '충남', '대전', '세종'],
                    '전북': ['전라북도', '전북', '전북특별자치도'],
                    '전남': ['전라남도', '전남'],
                    '전라': ['전라북도', '전북', '전라남도', '전남', '광주'],
                    '경북': ['경상북도', '경북'],
                    '경남': ['경상남도', '경남'],
                    '경상': ['경상북도', '경북', '경상남도', '경남', '부산', '울산', '대구'],
                    '제주': ['제주'],
                    '창원': ['창원'],
                    '함안': ['함안'],
                    '거제': ['거제'],
                    '김해': ['김해'],
                    '청주': ['청주'],
                    '천안': ['천안'],
                }
                
                match_regions = region_mapping.get(region, [region])
                
                for match_region in match_regions:
                    if match_region in inst_name:
                        region_match = True
                        break
                
                if not region_match:
                    continue

            # 카테고리 필터링
            if category:
                policy_category = policy.get('lclsfNm', '')
                if category not in policy_category:
                    continue

            # 키워드 필터링
            if keyword:
                policy_name = policy.get('plcyNm', '')
                policy_content = policy.get('plcyExplnCn', '')
                if keyword not in policy_name and keyword not in policy_content:
                    continue

            policy['source'] = '온통청년'
            filtered_policies.append(policy)

        # 다양성: 랜덤 섞기
        if len(filtered_policies) > max_results:
            random.shuffle(filtered_policies)
            filtered_policies = filtered_policies[:max_results]

        return filtered_policies

    def format_policy(self, policy: Dict) -> str:
        """정책 정보 형식"""
        return f"""
📌 **{policy.get('plcyNm', '정책명 없음')}** [온통청년]

🏢 주관기관: {policy.get('sprvsnInstCdNm', '정보 없음')}
📅 신청기간: {policy.get('aplyYmd', '상시 신청 가능')}
👥 나이: {policy.get('sprtTrgtMinAge', '?')}세 ~ {policy.get('sprtTrgtMaxAge', '?')}세

🔗 상세정보: {policy.get('refUrlAddr1', '링크 없음')}
{'='*80}
"""

# ============================
# 2. 기업마당 API 연동
# ============================

class BizinfoPolicyAPI:
    def __init__(self, api_key: str):
        self.api_url = "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do"
        self.api_key = api_key

    def get_policies(self, max_count: int = 100) -> List[Dict]:
        """기업마당 정책 데이터"""
        params = {
            "crtfcKey": self.api_key,
            "dataType": "json",
            "pageUnit": max_count,
            "pageIndex": 1
        }
        headers = {"User-Agent": "Mozilla/5.0"}

        try:
            response = requests.get(self.api_url, params=params, headers=headers, timeout=20)
            if response.status_code != 200:
                return []

            data = response.json()
            items = None
            if "jsonArray" in data:
                arr = data["jsonArray"]
                if isinstance(arr, dict) and "item" in arr:
                    items = arr["item"]
                elif isinstance(arr, list):
                    items = arr

            if not items:
                return []

            policies = []
            for item in items:
                policy = {
                    "title": item.get("pblancNm", "N/A"),
                    "agency": item.get("jrsdInsttNm", "N/A"),
                    "category": item.get("pldirSportRealmLclasCodeNm", "N/A"),
                    "summary": item.get("bsnsSumryCn", "N/A"),
                    "period": item.get("rceptPrdCn", "N/A"),
                    "url": "https://www.bizinfo.go.kr" + item.get("pblancUrl", ""),
                    "source": "기업마당"
                }
                policies.append(policy)

            return policies

        except Exception as e:
            print(f"기업마당 API 요청 오류: {e}")
            return []

    def search_policies(self, keyword: str = None, category: str = None, max_results: int = 3) -> List[Dict]:
        """조건에 맞는 정책 검색"""
        all_policies = self.get_policies(max_count=100)
        filtered = []

        for policy in all_policies:
            title = policy["title"].lower()
            summary = policy["summary"].lower()

            if keyword and keyword.lower() not in title and keyword.lower() not in summary:
                continue

            if category and category not in policy["category"]:
                continue

            filtered.append(policy)

        if len(filtered) > max_results:
            random.shuffle(filtered)
            filtered = filtered[:max_results]

        return filtered

    def format_policy(self, policy: Dict) -> str:
        """카드 형식"""
        clean_summary = re.sub('<[^<]+?>', '', policy.get("summary", ""))

        return f"""
🏢 **{policy["title"]}** [기업마당]

기관: {policy["agency"]}
분야: {policy["category"]}

🔗 상세 보기: {policy["url"]}
{'='*80}
"""

# ============================
# 3. 알리오 플러스 API 연동
# ============================

class AlioplusPolicyAPI:
    def __init__(self, api_key: str):
        self.api_url = "http://openapi.alioplus.go.kr/api/business"
        self.api_key = api_key.replace("+", "%2B")

    def get_policies(self, max_count: int = 100) -> List[Dict]:
        """알리오 플러스 사업 정보"""
        params = {
            "X-API-AUTH-KEY": self.api_key,
            "pageSize": str(max_count)
        }
        
        try:
            response = requests.post(self.api_url, data=params, timeout=20)
            if response.status_code != 200:
                print(f"알리오 플러스 API 상태 코드: {response.status_code}")
                return []

            data = response.json()
            
            items = []
            if isinstance(data, dict):
                items = data.get('list', data.get('data', []))
            elif isinstance(data, list):
                items = data
            
            if not items or not isinstance(items, list):
                print(f"알리오 플러스: 예상치 못한 데이터 형식 - {type(items)}")
                return []

            policies = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                    
                policy = {
                    "title": item.get("bsnNa", "N/A"),
                    "agency": item.get("apbaNa", "N/A"),
                    "summary": item.get("bsnDsc", "N/A"),
                    "lifecycle": item.get("lifeCycleNa", "N/A"),
                    "target": item.get("guideTar", "N/A"),
                    "method": item.get("guideMth", "N/A"),
                    "inquiry": item.get("guideDsc", "N/A"),
                    "url": item.get("siteUrl", ""),
                    "category": item.get("svcCateNa", "N/A"),
                    "source": "알리오플러스"
                }
                policies.append(policy)

            print(f"✅ 알리오 플러스: {len(policies)}개 정책 로드 성공")
            return policies

        except Exception as e:
            print(f"알리오 플러스 API 요청 오류: {e}")
            import traceback
            traceback.print_exc()
            return []

    def search_policies(self, keyword: str = None, lifecycle: str = None, max_results: int = 2) -> List[Dict]:
        """조건에 맞는 사업 검색"""
        all_policies = self.get_policies(max_count=100)
        filtered = []

        for policy in all_policies:
            title = policy["title"].lower()
            summary = policy["summary"].lower()

            if keyword and keyword.lower() not in title and keyword.lower() not in summary:
                continue

            if lifecycle and lifecycle not in policy["lifecycle"]:
                continue

            filtered.append(policy)

        if len(filtered) > max_results:
            random.shuffle(filtered)
            filtered = filtered[:max_results]

        return filtered

    def format_policy(self, policy: Dict) -> str:
        """카드 형식"""
        clean_summary = re.sub('<[^<]+?>', '', policy.get("summary", ""))
        
        if len(clean_summary) > 100:
            clean_summary = clean_summary[:100] + "..."

        return f"""
🛍️ **{policy["title"]}** [알리오플러스]

기관: {policy["agency"]}
생애주기: {policy["lifecycle"]}
대상: {policy["target"]}

📝 {clean_summary}

🔗 상세 보기: {policy["url"] if policy["url"] else "정보 없음"}
{'='*80}
"""

# ============================
# 4. KULLM 모델
# ============================

class KULLMChatbot:
    def __init__(self, model_name: str = "nlpai-lab/KULLM-Polyglot-5.8B-v2"):
        """KULLM 모델 초기화"""
        if not TRANSFORMERS_AVAILABLE:
            raise ImportError("transformers와 torch가 필요합니다!")
        
        print("\n" + "="*60)
        print("🤖 KULLM 5.8B-v2 모델 로딩 시작...")
        print("="*60)
        print("⏳ 토크나이저 로딩 중...")

        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        print("✅ 토크나이저 로딩 완료!")
        
        print("⏳ 모델 로딩 중... (첫 실행: 3-10분, 이후: 1-2분)")
        
        if torch.cuda.is_available():
            print("   🚀 GPU 감지됨! GPU 모드로 로딩...")
            self.model = AutoModelForCausalLM.from_pretrained(
                model_name,
                torch_dtype=torch.float16,
                low_cpu_mem_usage=True
            )
            self.model = self.model.to('cuda')
            print("   ✅ GPU 모드 활성화")
        else:
            print("   💻 CPU 모드로 로딩...")
            self.model = AutoModelForCausalLM.from_pretrained(
                model_name,
                torch_dtype=torch.float32,
                low_cpu_mem_usage=True
            )
            self.model = self.model.to('cpu')
            print("   ✅ CPU 모드 활성화")

        print("="*60)
        print("✅ KULLM 모델 완전히 로딩 완료!")
        print("="*60 + "\n")

    def clean_response(self, text: str) -> str:
        patterns = [
            r'\b(User|사용자)\s*:\s*.*?\n',
            r'\b(Assistant|Chatbot|챗봇)\s*:\s*',
            r'\b(Q|질문)\s*:\s*.*?\n',
            r'\b(A|답변)\s*:\s*'
        ]
        for p in patterns:
            text = re.sub(p, '', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        return text

    def generate_response(self, prompt: str, max_new_tokens: int = 120) -> str:
        """✅ 짧고 간결한 응답 (120 토큰)"""
        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=512,
            return_token_type_ids=False
        )
        if torch.cuda.is_available():
            inputs = {k: v.to("cuda") for k, v in inputs.items()}

        with torch.inference_mode():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=0.6,
                top_p=0.9,
                do_sample=True,
                pad_token_id=self.tokenizer.eos_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                repetition_penalty=1.12,
                no_repeat_ngram_size=3
            )

        text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)

        if text.startswith(prompt):
            text = text[len(prompt):].lstrip()

        for stop in ["\n\nUser:", "\n\n사용자:", "\n\nQ:", "\n\n질문:"]:
            if stop in text:
                text = text.split(stop, 1)[0].rstrip()
                break

        text = self.clean_response(text)
        if not text or len(text) < 10:
            text = "더 구체적으로 질문해주시면 도움을 드리겠습니다."
        return text
    
# ============================
# 5. 통합 챗봇 시스템
# ============================

class UnifiedPolicyChatbot:
    def __init__(self, youth_api_key: str, bizinfo_api_key: str, alioplus_api_key: str, use_kullm: bool = True):
        self.youth_api = YouthPolicyAPI(youth_api_key)
        self.bizinfo_api = BizinfoPolicyAPI(bizinfo_api_key)
        self.alioplus_api = AlioplusPolicyAPI(alioplus_api_key)
        self.kullm = None
        self.use_kullm = use_kullm and TRANSFORMERS_AVAILABLE
        self.kullm_loaded = False

    def load_kullm(self):
        """KULLM 모델 로드"""
        if not self.use_kullm:
            print("ℹ️ KULLM 사용 안 함 (검색 모드)")
            return False
        
        try:
            self.kullm = KULLMChatbot()
            self.kullm_loaded = True
            print("\n🎉 KULLM 준비 완료! 자연스러운 대화가 가능합니다!\n")
            return True
        except Exception as e:
            print(f"\n❌ KULLM 로딩 실패: {e}")
            print("⚠️ 검색 모드로 전환합니다.\n")
            self.kullm = None
            self.kullm_loaded = False
            return False

    def extract_user_info(self, message: str) -> Dict:
        """사용자 정보 추출"""
        info = {
            'age': None,
            'region': None,
            'category': None,
            'keyword': None,
            'target': 'both',
            'explicit_search': False,
            'all_ages': False,
            'max_results': 3 # ✅ 기본 3개
        }

        # 전연령 키워드
        all_age_keywords = ['전연령', '모든 연령', '연령무관', '연령 무관', '나이무관', '나이 무관']
        if any(kw in message for kw in all_age_keywords):
            info['all_ages'] = True

        # ✅ 정책 개수 추출
        count_match = re.search(r'(\d+)개', message)
        if count_match:
            requested_count = int(count_match.group(1))
            if 1 <= requested_count <= 20:
                info['max_results'] = requested_count
                print(f"[INFO] 요청 개수: {requested_count}개")

        # 나이 추출
        age_patterns = [
            (r'(\d{1,2})대', 'decade'),
            (r'(\d{2})살', 'exact'),
            (r'(\d{2})세', 'exact'),
            (r'나이[는]?\s*(\d{2})', 'exact'),
        ]

        for pattern, pattern_type in age_patterns:
            match = re.search(pattern, message)
            if match:
                age_val = int(match.group(1))

                if pattern_type == 'decade':
                    if 1 <= age_val <= 12:
                        info['age'] = age_val * 10 + 5
                    else:
                        continue
                else:
                    if 0 <= age_val <= 120:
                        info['age'] = age_val
                    else:
                        continue

                print(f"[INFO] 추출된 나이: {info['age']}세")
                break

        # 지역 추출
        regions = {
            '서울': '서울', '부산': '부산', '대구': '대구', '인천': '인천',
            '광주': '광주', '대전': '대전', '울산': '울산', '세종': '세종',
            '경기': '경기', '강원': '강원', '충북': '충북', '충남': '충남',
            '충청': '충청', '전북': '전북', '전남': '전남', '전라': '전라',
            '경북': '경북', '경남': '경남', '경상': '경상', '제주': '제주',
            '창원': '창원', '거제': '거제', '함안': '함안', '청주': '청주',
            '천안': '천안', '김해': '김해',
        }

        for region_keyword, region_value in regions.items():
            if region_keyword in message:
                info['region'] = region_value
                break

        # 대상 구분
        if any(word in message for word in ['노인', '어르신', '고령', '시니어']):
            info['target'] = 'senior'
        elif any(word in message for word in ['기업', '사업자', '중소기업']):
            info['target'] = 'business'
        elif any(word in message for word in ['청년', '취업', '대학생']):
            info['target'] = 'youth'

        # 키워드 추출
        keywords = [
            '창업', '취업', '주거', '자격증', '대출', '교육', 'R&D',
            '면접', '전세', '월세', '훈련', '인턴', '채용', '장려금', '생활비',
            '노인', '어르신', '복지', '지원', '돌봄', '건강', '의료', '요양',
            '일자리', '구직', '청년', '고용', '직업', '기술', '연구', '개발'
        ]
        for kw in keywords:
            if kw in message:
                info['keyword'] = kw
                break

        # ✅ 명시적 검색 감지 (개선된 로직)
        policy_keywords = ['정책', '지원', '사업', '프로그램', '혜택', '보조금']
        has_policy_context = any(kw in message for kw in policy_keywords)

        # 정책 검색 명령 동사: '찾아', '검색', '뽑아', '추천', '보여' 등
        search_verbs = ['찾아', '검색', '뽑아', '추천', '보여', '달라']
        has_search_verb = any(verb in message for verb in search_verbs)
        
        # 일반적인 질문 동사: '알려', '궁금', '뭐야', '이유', '장점', '단점', '의미', '정의', '설명'
        general_verbs = ['알려', '궁금', '뭐야', '이유', '장점', '단점', '의미', '정의', '설명']
        is_general_query = any(verb in message for verb in general_verbs)

        # 명시적 검색 조건: 
        # 1. 정책 키워드 + 명시적 검색 동사 (예: 취업 정책 찾아줘)
        # 2. 정책 키워드 + 사용자 정보(나이, 지역, 키워드 등) + 일반 질문 동사 **없음** (예: 25살 창원 취업 정책)
        info['explicit_search'] = (has_policy_context and has_search_verb) or \
                                  (has_policy_context and (info['age'] or info['region'] or info['keyword']) and not is_general_query)
        
        # '줘', '주세요'가 포함된 경우 (정책 키워드가 있으면 검색으로, 없으면 일반 대화로 유도)
        if ('줘' in message or '주세요' in message) and has_policy_context:
            info['explicit_search'] = True
        
        # 하지만 '이유'나 '뭐야'가 포함된 질문은 명확한 정책 검색보다는 일반 질문으로 간주 (KULLM이 처리하도록 유도)
        if '이유' in message or '뭐야' in message or '설명' in message:
            info['explicit_search'] = False

        # 일반 인사/대화는 검색 대상에서 제외
        if message.strip().lower() in ['안녕', '안녕하세요', 'hi', '헬로', '뭐해', '잘가']:
            info['explicit_search'] = False

        return info

    def search_policies(self, user_info: Dict) -> str:
        """정책 검색"""
        all_policies = []
        
        age = user_info.get('age')
        target = user_info['target']
        all_ages = user_info.get('all_ages', False)
        max_results = user_info.get('max_results', 3)  # ✅
        
        # 각 API별 할당
        results_per_api = max(3, max_results * 2)
        
        # 청년 정책
        if target in ['youth', 'both']:
            if all_ages or age is None or (age and age <= 39):
                # max_results 대신 results_per_api 사용
                youth_policies = self.youth_api.search_policies(
                    age=age if not all_ages else None,
                    region=user_info.get('region'),
                    keyword=user_info.get('keyword'),
                    max_results=results_per_api, # 넉넉하게 요청
                    all_ages=all_ages
                )
                all_policies.extend(youth_policies)

        # 기업/일반 정책
        if target in ['business', 'both', 'senior']:
            # max_results 대신 results_per_api 사용
            bizinfo_policies = self.bizinfo_api.search_policies(
                keyword=user_info.get('keyword'),
                max_results=results_per_api # 넉넉하게 요청
            )
            all_policies.extend(bizinfo_policies)

            # max_results 대신 results_per_api 사용
            alioplus_policies = self.alioplus_api.search_policies(
                keyword=user_info.get('keyword'),
                max_results=results_per_api # 넉넉하게 요청
            )
            all_policies.extend(alioplus_policies)
        
        # 중복 제거 (간단하게)
        seen_urls = set()
        unique_policies = []
        for policy in all_policies:
            # 온통청년: refUrlAddr1, 기업마당/알리오플러스: url
            url = policy.get('refUrlAddr1') or policy.get('url')
            if url and url not in seen_urls:
                unique_policies.append(policy)
                seen_urls.add(url)
            elif not url:
                # URL이 없으면 일단 포함 (정확한 중복 제거 어려움)
                unique_policies.append(policy) 

        all_policies = unique_policies

        # ✅ 최종 개수 조정
        if len(all_policies) > max_results:
            random.shuffle(all_policies)
            all_policies = all_policies[:max_results]

        if not all_policies:
            if age and age > 39:
                return f"""
죄송합니다. {age}세를 대상으로 하는 정책을 찾지 못했습니다.

💡 안내:
- 온통청년 API는 주로 39세 이하를 대상으로 합니다
- 다른 키워드로 다시 검색해보세요!
"""
            return ""

        result = f"\n\n✨ **관련 정책 {len(all_policies)}개:**\n"
        
        for policy in all_policies:
            source = policy.get('source', '')
            
            if source == '온통청년':
                result += self.youth_api.format_policy(policy)
            elif source == '기업마당':
                result += self.bizinfo_api.format_policy(policy)
            elif source == '알리오플러스':
                result += self.alioplus_api.format_policy(policy)

        return result

    def chat(self, message: str, history: List) -> str:
        """챗봇 메인 로직"""
        
        # 간단한 인사
        if message.strip() in ['안녕', '안녕하세요', 'hi', '헬로']:
            if self.kullm_loaded:
                return "안녕하세요! 😊 청년 및 기업 정책 추천 챗봇입니다.\n무엇을 도와드릴까요?"
            else:
                return "안녕하세요! 😊 정책 검색 챗봇입니다.\n'25살 창원 취업 정책 찾아줘'처럼 구체적으로 말씀해주세요!"

        # 사용자 정보 추출
        user_info = self.extract_user_info(message)

        # 명시적 검색이면 바로 정책 검색
        if user_info['explicit_search']:
            print("[명시적 검색] 정책 검색 수행...")
            policy_results = self.search_policies(user_info)
            if policy_results:
                return "관련 정책을 찾아드렸습니다!" + policy_results
            else:
                return "조건에 맞는 정책을 찾지 못했습니다.\n다른 키워드로 다시 검색해보세요!"

        # KULLM은 일반 대화만
        if self.kullm_loaded and self.kullm is not None:
            try:
                prompt = (
                    "너는 한국어로 자연스럽게 답하는 정책 안내 AI다. "
                    "자문자답이나 역할 표시 없이, 완전한 문장으로 답해라.\n\n"
                    f"질문: {message}\n\n답변:"
                )

                print("[KULLM] 응답 생성 중...")
                kullm_response = self.kullm.generate_response(prompt, max_new_tokens=120)
                print(f"[KULLM] ✅ 응답 완료")
                return kullm_response

            except Exception as e:
                print(f"[KULLM] ❌ 오류: {e}")
                return "죄송합니다. 응답 생성 중 문제가 발생했습니다."

        # KULLM 없으면 안내
        return "구체적으로 말씀해주시면 정책을 찾아드리겠습니다!"


# ============================
# 6. Flask API
# ============================
app = Flask(__name__)
app.secret_key = "your_secret_key_here"
global_chatbot = None

@app.route("/")
def home():
    return "<h1>🎯 통합 정책 추천 챗봇 API</h1>"

@app.route("/api/message", methods=["POST"])
def api_message():
    global global_chatbot
    if global_chatbot is None:
        return jsonify({"error": "Chatbot not initialized"}), 500

    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"error": "Missing 'message' parameter"}), 400

    # 🔹 사용자 입력 전처리
    user_message = str(data["message"]).strip()
    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    # 🔹 기존 chat() 로직 그대로 사용
    try:
        response = global_chatbot.chat(user_message, history=[])
        return jsonify({"response": response, "status": "success"})
    except Exception as e:
        return jsonify({"error": str(e), "status": "error"}), 500


# ============================
# 7. 메인
# ============================
if __name__ == "__main__":
    YOUTH_API_KEY = "fa19e38e-58a0-4847-b18a-a8e272bd8f40"
    BIZINFO_API_KEY = "gQ0k25"
    ALIOPLUS_API_KEY = "XUUrvIcCpSVWkp0wLH8gPebTAOIJLfwmTgdWoEcFUSQ="
    USE_KULLM = True

    global_chatbot = UnifiedPolicyChatbot(YOUTH_API_KEY, BIZINFO_API_KEY, ALIOPLUS_API_KEY, use_kullm=USE_KULLM)
    if USE_KULLM:
        global_chatbot.load_kullm()

    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
