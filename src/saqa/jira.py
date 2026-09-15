"""Secure Jira Cloud integration for CI verification and controlled write-back."""
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Any, Iterable
import httpx
@dataclass(frozen=True, slots=True)
class JiraConfig:
    base_url:str; email:str; api_token:str; project_key:str
    @classmethod
    def from_env(cls)->"JiraConfig":
        values={"base_url":os.getenv("JIRA_BASE_URL","").strip().rstrip("/"),"email":os.getenv("JIRA_EMAIL","").strip(),"api_token":os.getenv("JIRA_API_TOKEN",""),"project_key":os.getenv("JIRA_PROJECT_KEY","").strip()}
        missing=[k for k,v in values.items() if not v]
        if missing: raise ValueError("Missing Jira configuration: "+", ".join(missing))
        if not values["base_url"].startswith("https://"): raise ValueError("JIRA_BASE_URL must use HTTPS")
        return cls(**values)
@dataclass(frozen=True, slots=True)
class JiraProjectResult: key:str; name:str; project_type:str
@dataclass(frozen=True, slots=True)
class JiraIssueResult: key:str; id:str; url:str
@dataclass(frozen=True, slots=True)
class JiraIssueState: key:str; status:str; labels:tuple[str,...]
class JiraClient:
    def __init__(self,config:JiraConfig,timeout:float=15.0)->None:
        self.config=config; self._client=httpx.Client(base_url=config.base_url,auth=(config.email,config.api_token),headers={"Accept":"application/json","Content-Type":"application/json"},timeout=timeout,follow_redirects=False)
    def close(self)->None:self._client.close()
    def __enter__(self)->"JiraClient":return self
    def __exit__(self,*_:object)->None:self.close()
    def _raise_for_auth(self,response:httpx.Response,action:str)->None:
        if response.status_code in {401,403}: raise RuntimeError(f"Jira {action} authorization failed (HTTP {response.status_code})")
    def verify_access(self)->JiraProjectResult:
        response=self._client.get(f"/rest/api/3/project/{self.config.project_key}"); self._raise_for_auth(response,"authentication"); response.raise_for_status(); payload=response.json(); return JiraProjectResult(str(payload.get("key","")),str(payload.get("name","")),str(payload.get("projectTypeKey","")))
    def find_project_issues(self,max_results:int=1000)->dict[str,JiraIssueResult]:
        if max_results<=0: raise ValueError("max_results must be positive")
        issues:list[dict[str,Any]]=[]; next_token=None
        while True:
            params:dict[str,Any]={"jql":f"project = {self.config.project_key}","maxResults":min(max_results,100),"fields":"summary,labels"}
            if next_token: params["nextPageToken"]=next_token
            response=self._client.get("/rest/api/3/search/jql",params=params); self._raise_for_auth(response,"authentication"); response.raise_for_status(); payload=response.json(); page=payload.get("issues",[]) if isinstance(payload,dict) else []
            if isinstance(page,list): issues.extend(i for i in page if isinstance(i,dict))
            if len(issues)>=max_results or not isinstance(payload,dict) or not payload.get("nextPageToken"): break
            next_token=str(payload["nextPageToken"])
        result={}
        for item in issues[:max_results]:
            key=str(item.get("key","")); summary=str(item.get("fields",{}).get("summary",""))
            if not key or not summary: continue
            if summary in result and result[summary].key!=key: raise RuntimeError(f"Jira has duplicate managed summary: {summary!r} ({result[summary].key}, {key})")
            result[summary]=JiraIssueResult(key,str(item.get("id","")),f"{self.config.base_url}/browse/{key}")
        return result
    def find_bootstrap_issues(self)->dict[str,JiraIssueResult]:
        response=self._client.get("/rest/api/3/search/jql",params={"jql":f"project = {self.config.project_key} AND labels = saqa-bootstrap","maxResults":100,"fields":"summary"}); self._raise_for_auth(response,"authentication"); response.raise_for_status(); return {str(i["fields"]["summary"]):JiraIssueResult(str(i["key"]),str(i["id"]),f"{self.config.base_url}/browse/{i['key']}") for i in response.json().get("issues",[]) if i.get("key") and i.get("fields",{}).get("summary")}
    def get_issue_state(self,issue_key:str)->JiraIssueState:
        response=self._client.get(f"/rest/api/3/issue/{issue_key}",params={"fields":"status,labels"}); self._raise_for_auth(response,"authentication"); response.raise_for_status(); fields=response.json().get("fields",{}); status=fields.get("status") or {}; return JiraIssueState(issue_key,str(status.get("name","")),tuple(str(x) for x in fields.get("labels",[]) or []))
    def get_issue_comments(self,issue_key:str)->list[dict[str,Any]]:
        response=self._client.get(f"/rest/api/3/issue/{issue_key}/comment",params={"maxResults":100,"orderBy":"-created"}); self._raise_for_auth(response,"authentication"); response.raise_for_status(); return list(response.json().get("comments",[]))
    def create_task(self,summary:str,description:str,labels:list[str])->JiraIssueResult:return self._create_issue("Task",summary,description,labels)
    def create_bug(self,summary:str,description:str,labels:list[str])->JiraIssueResult:return self._create_issue("Bug",summary,description,labels)
    def _create_issue(self,issue_type:str,summary:str,description:str,labels:list[str])->JiraIssueResult:
        payload={"fields":{"project":{"key":self.config.project_key},"issuetype":{"name":issue_type},"summary":summary,"description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[{"type":"text","text":description}]}]},"labels":labels}}; response=self._client.post("/rest/api/3/issue",json=payload); self._raise_for_auth(response,"write"); response.raise_for_status(); result=response.json(); key=str(result["key"]); return JiraIssueResult(key,str(result["id"]),f"{self.config.base_url}/browse/{key}")
    def update_labels(self,issue_key:str,*,add:Iterable[str]=(),remove:Iterable[str]=())->None:
        updates=[{"add":x} for x in add]+[{"remove":x} for x in remove]
        if not updates:return
        response=self._client.put(f"/rest/api/3/issue/{issue_key}",json={"update":{"labels":updates}}); self._raise_for_auth(response,"write"); response.raise_for_status()
    def add_comment_once(self,issue_key:str,body:str,marker:str)->bool:
        for comment in self.get_issue_comments(issue_key):
            if marker in str(comment):return False
        payload={"body":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[{"type":"text","text":body}]}]}}; response=self._client.post(f"/rest/api/3/issue/{issue_key}/comment",json=payload); self._raise_for_auth(response,"comment"); response.raise_for_status(); return True
    def transition_to_any(self,issue_key:str,target_statuses:Iterable[str])->str|None:
        response=self._client.get(f"/rest/api/3/issue/{issue_key}/transitions"); self._raise_for_auth(response,"authentication"); response.raise_for_status(); wanted={x.casefold() for x in target_statuses}; current=self.get_issue_state(issue_key).status
        for transition in response.json().get("transitions",[]):
            name=str(transition.get("name",""))
            if name.casefold() in wanted:
                if current.casefold()==name.casefold():return name
                tr=self._client.post(f"/rest/api/3/issue/{issue_key}/transitions",json={"transition":{"id":str(transition["id"])}}); self._raise_for_auth(tr,"transition write"); tr.raise_for_status(); return name
        return None

def verify_from_env()->JiraProjectResult:
    with JiraClient(JiraConfig.from_env()) as client:return client.verify_access()
