import type { Document, ResourceRef, Thread, TopicSummary } from '../../shared/api';

export type Topic = TopicSummary & {
  brief: Document;
  my_submission: { id:string; title:string; body:string; version:number; sources:ResourceRef[] } | null;
  progress: { member_id:string; status:'not_started'|'exploring'|'submitted' }[];
  explorations: Thread[];
  proposals: (Document & {proposal_id:string;author_id:string;proposal_version:number})[];
  decision: Document | null;
  handoffs: {target_id:string;thread_id:string;status:Thread['status']}[];
};
export const stageLabels = { exploring:'独立探索', reviewing:'比较方案', decided:'已决策' };
export const proposalDraftKey = (uid:string,rid:string)=>`accord.proposal.${uid}.${rid}`;
