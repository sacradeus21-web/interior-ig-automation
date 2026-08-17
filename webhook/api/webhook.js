// 댓글 -> 비공개 답장(팔로우+답장 요청) -> 답장 오면 PDF 발송, 흐름을 처리하는
// Instagram 웹훅 수신 엔드포인트. Vercel Node 서버리스 함수로 배포된다.
//
// 필요 환경변수:
//   IG_ACCESS_TOKEN        - graph.instagram.com용 장기 액세스 토큰
//   IG_BUSINESS_ACCOUNT_ID - sweet.studio_official의 IG 사용자 ID
//   IG_APP_SECRET          - 웹훅 서명(X-Hub-Signature-256) 검증용 앱 시크릿
//   WEBHOOK_VERIFY_TOKEN   - 메타 대시보드에 등록할 임의의 검증 토큰
//   PDF_URL                - 발송할 PDF의 공개 URL (raw.githubusercontent.com)
//
// 팔로우 여부는 Instagram API가 지원하지 않아 실제로 검증하지 않는다(양심제) -
// 비공개 답장에서 "팔로우 후 답장해주세요"라고만 안내하고, 그 이후 오는 첫
// 메시지에는 무조건 PDF를 보낸다.

const crypto = require("crypto");

export const config = {
  api: { bodyParser: false },
};

const GRAPH_API_VERSION = "v21.0";

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

async function sendPrivateReply(commentId, text) {
  const url = `https://graph.instagram.com/${GRAPH_API_VERSION}/${process.env.IG_BUSINESS_ACCOUNT_ID}/messages`;
  const body = {
    recipient: { comment_id: commentId },
    message: { text },
  };
  const resp = await fetch(url + `?access_token=${process.env.IG_ACCESS_TOKEN}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    console.error("private reply 실패", await resp.text());
  }
}

async function sendPdf(recipientId) {
  const url = `https://graph.instagram.com/${GRAPH_API_VERSION}/${process.env.IG_BUSINESS_ACCOUNT_ID}/messages`;
  const body = {
    recipient: { id: recipientId },
    message: {
      attachment: {
        type: "file",
        payload: { url: process.env.PDF_URL },
      },
    },
  };
  const resp = await fetch(url + `?access_token=${process.env.IG_ACCESS_TOKEN}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    console.error("PDF 발송 실패", await resp.text());
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

  // 항상 즉시 200 반환 대상이므로, 실제 처리는 응답 이후에도 계속 진행되도록
  // await 없이 fire-and-forget 하지 않고 여기서 끝까지 처리한 뒤 응답한다
  // (Vercel 서버리스는 응답 후 즉시 함수가 종료될 수 있어 순서를 지켜야 함).
  try {
    for (const entry of payload.entry || []) {
      if (entry.field === "comments" && entry.value) {
        const comment = entry.value;
        // 우리 계정 자신이 남긴 댓글(답글 등)은 무시
        if (comment.from && comment.from.id !== process.env.IG_BUSINESS_ACCOUNT_ID) {
          await sendPrivateReply(
            comment.id,
            "댓글 감사해요! 🙂 저희 계정 팔로우하시고 이 메시지에 아무 답장이나 주시면, 오늘 소개해드린 제품 정리 자료를 PDF로 보내드릴게요."
          );
        }
      }

      for (const m of entry.messaging || []) {
        if (!m.message || m.message.is_echo) continue;
        if (m.sender && m.sender.id === process.env.IG_BUSINESS_ACCOUNT_ID) continue;
        await sendPdf(m.sender.id);
      }
    }
  } catch (e) {
    console.error("웹훅 처리 중 오류", e);
  }

  res.status(200).send("ok");
};
