// 댓글 -> 비공개 답장(팔로우 안내) -> "팔로우했어요." 버튼(또는 아무 답장) ->
// 자료 발송, 흐름을 처리하는 Instagram 웹훅 수신 엔드포인트.
// Vercel Node 서버리스 함수로 배포된다.
//
// 필요 환경변수:
//   IG_ACCESS_TOKEN        - graph.instagram.com용 장기 액세스 토큰
//   IG_BUSINESS_ACCOUNT_ID - sweet.studio_official의 IG 사용자 ID
//   IG_APP_SECRET          - 웹훅 서명(X-Hub-Signature-256) 검증용 앱 시크릿
//   WEBHOOK_VERIFY_TOKEN   - 메타 대시보드에 등록할 임의의 검증 토큰
//   PDF_URL                - 발송할 PDF의 공개 URL (raw.githubusercontent.com)
//
// 팔로우 여부는 Instagram API가 지원하지 않아 실제로 검증하지 않는다(양심제) -
// "팔로우했어요." 버튼을 누르거나(postback) 아무 메시지나 답장하면(일반
// 텍스트) 그대로 믿고 자료를 보낸다.

const crypto = require("crypto");

export const config = {
  api: { bodyParser: false },
};

const GRAPH_API_VERSION = "v21.0";
const FOLLOW_CONFIRM_PAYLOAD = "CONFIRM_FOLLOWED";

function readRawBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

function verifySignature(rawBody, signatureHeader, appSecret) {
  if (!signatureHeader) return false;
  const expected =
    "sha256=" +
    crypto.createHmac("sha256", appSecret).update(rawBody).digest("hex");
  const a = Buffer.from(expected);
  const b = Buffer.from(signatureHeader);
  if (a.length !== b.length) return false;
  return crypto.timingSafeEqual(a, b);
}

async function callMessagesApi(body, label) {
  const url = `https://graph.instagram.com/${GRAPH_API_VERSION}/${process.env.IG_BUSINESS_ACCOUNT_ID}/messages`;
  const resp = await fetch(url + `?access_token=${process.env.IG_ACCESS_TOKEN}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    console.error(`${label} 실패`, await resp.text());
    return false;
  }
  return true;
}

// 비공개 답장은 대화창을 열지 않아서, 답장 직후 별도 메시지로 버튼을
// 보내면 "outside of allowed window" 에러로 실패한다 (실측 확인됨).
// 그래서 안내 문구 + 팔로우 확인 버튼을 하나의 제네릭 템플릿 메시지로
// 합쳐서 비공개 답장 자체로 보낸다.
async function sendPrivateReply(commentId) {
  return callMessagesApi(
    {
      recipient: { comment_id: commentId },
      message: {
        attachment: {
          type: "template",
          payload: {
            template_type: "generic",
            elements: [
              {
                title: "댓글 남겨주셔서 감사합니다🙌 콘텐츠는 팔로워분들에게 보내드리고 있어요. 저를 팔로우해주셨다면 아래 버튼을 클릭해주세요!",
                buttons: [
                  {
                    type: "postback",
                    title: "팔로우했어요.",
                    payload: FOLLOW_CONFIRM_PAYLOAD,
                  },
                ],
              },
            ],
          },
        },
      },
    },
    "private reply"
  );
}

// 파일 첨부(type:"file")는 raw.githubusercontent.com처럼 Content-Type이
// application/octet-stream으로 내려오는 호스팅에서 "첨부파일 형식을 지원하지
// 않음" 에러로 실패했다(실측 확인) - 그래서 파일 첨부 대신, 자료를 보여주는
// 간단한 웹페이지로 연결되는 링크 버튼을 보낸다. PDF_URL은 이제 그 페이지의
// URL을 가리킨다(이름은 그대로 두되 값만 웹페이지 주소로 교체해서 사용).
async function sendResource(recipientId) {
  await callMessagesApi(
    {
      recipient: { id: recipientId },
      message: {
        attachment: {
          type: "template",
          payload: {
            template_type: "generic",
            elements: [
              {
                title: "자료 보내드려요! 정성껏 조사한 내용이에요🙂 앞으로도 유용한 인테리어 정보만 드릴게요.",
                buttons: [
                  {
                    type: "web_url",
                    title: "자료 보러가기",
                    url: process.env.PDF_URL,
                  },
                ],
              },
            ],
          },
        },
      },
    },
    "자료 링크 발송"
  );
}

async function handleComment(comment) {
  // 우리 계정 자신이 남긴 댓글(답글 등)은 무시
  if (!comment.from || comment.from.id === process.env.IG_BUSINESS_ACCOUNT_ID) return;
  await sendPrivateReply(comment.id);
}

async function handleMessagingEvent(m) {
  if (!m.sender || m.sender.id === process.env.IG_BUSINESS_ACCOUNT_ID) return;

  if (m.postback) {
    if (m.postback.payload === FOLLOW_CONFIRM_PAYLOAD) {
      await sendResource(m.sender.id);
    }
    return;
  }

  if (m.message && !m.message.is_echo) {
    // 버튼 대신 그냥 텍스트로 답장하는 경우도 그대로 자료를 보낸다.
    await sendResource(m.sender.id);
  }
}

module.exports = async (req, res) => {
  if (req.method === "GET") {
    const mode = req.query["hub.mode"];
    const token = req.query["hub.verify_token"];
    const challenge = req.query["hub.challenge"];
    if (mode === "subscribe" && token === process.env.WEBHOOK_VERIFY_TOKEN) {
      res.status(200).send(challenge);
    } else {
      res.status(403).send("verification failed");
    }
    return;
  }

  if (req.method !== "POST") {
    res.status(405).send("method not allowed");
    return;
  }

  const rawBody = await readRawBody(req);
  const signature = req.headers["x-hub-signature-256"];
  if (!verifySignature(rawBody, signature, process.env.IG_APP_SECRET)) {
    res.status(401).send("invalid signature");
    return;
  }

  let payload;
  try {
    payload = JSON.parse(rawBody.toString("utf8"));
  } catch (e) {
    res.status(400).send("bad json");
    return;
  }

  // Meta는 이 페이로드를 최상위가 단일 객체({object, entry:[...]})인 경우와
  // 배열([{object, entry:[...]}, ...])인 경우가 둘 다 있어서 두 형태 모두
  // 처리해야 한다 (배열 형태를 놓쳐서 조용히 아무 것도 안 하는 버그가 있었음).
  const batches = Array.isArray(payload) ? payload : [payload];
  console.log("웹훅 수신", JSON.stringify(batches).slice(0, 1000));

  // 항상 즉시 200 반환 대상이므로, 실제 처리는 응답 이후에도 계속 진행되도록
  // await 없이 fire-and-forget 하지 않고 여기서 끝까지 처리한 뒤 응답한다
  // (Vercel 서버리스는 응답 후 즉시 함수가 종료될 수 있어 순서를 지켜야 함).
  try {
    const entries = batches.flatMap((b) => b.entry || []);
    for (const entry of entries) {
      // 계정 유형/API 버전에 따라 최상위 field/value 형태와 고전적인
      // changes[] 래퍼 형태가 둘 다 관측돼서 둘 다 지원한다.
      const commentChanges = entry.field === "comments" && entry.value
        ? [entry.value]
        : (entry.changes || []).filter((c) => c.field === "comments").map((c) => c.value);

      for (const comment of commentChanges) {
        await handleComment(comment);
      }

      for (const m of entry.messaging || []) {
        await handleMessagingEvent(m);
      }
    }
  } catch (e) {
    console.error("웹훅 처리 중 오류", e);
  }

  res.status(200).send("ok");
};
