// A TASK THAT JOINED A SECOND PERSON'S THREAD (2026-11-02) can hold a reply to each - one at a time (cardqueue.py), each saying whom it answers.
// the task's message a pending reply answers - the mail that asked (AnswersMid), else its own MessageId - or null when it is not one of them
export const draftAnswers = (review, messages = []) => {
  const mid = review?.AnswersMid || review?.MessageId;
  return (mid && messages.find((m) => m.MessageId === mid)) || null;
};
