/**
 * Claude 응답에서 JSON을 추출하는 공유 유틸리티.
 * ClaudeClient, ClaudeCliClient, LocalModelClient 모두 사용한다.
 */

/** 마크다운 코드 블록 또는 raw JSON을 추출한다. */
export function extractJSON(text: string): string {
  // 1. 마크다운 코드 블록 내부 JSON (CRLF 호환)
  const codeBlockMatch = text.match(/```(?:json)?\s*\r?\n?([\s\S]*?)\r?\n?```/);
  if (codeBlockMatch) return codeBlockMatch[1]!.trim();

  // 2. 첫 번째 { 또는 [ 부터 balanced extraction
  const firstBrace = text.indexOf('{');
  const firstBracket = text.indexOf('[');

  const startIdx =
    firstBracket !== -1 && (firstBrace === -1 || firstBracket < firstBrace)
      ? firstBracket
      : firstBrace;

  if (startIdx !== -1) {
    const extracted = extractBalancedJSON(text, startIdx);
    if (extracted) return extracted;
  }

  return text.trim();
}

/** 중괄호/대괄호 깊이를 추적하여 완전한 JSON 문자열을 추출한다. */
function extractBalancedJSON(text: string, start: number): string | null {
  const open = text[start];
  const close = open === '{' ? '}' : ']';
  let depth = 0;
  let inString = false;
  let escape = false;

  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (escape) {
      escape = false;
      continue;
    }
    if (ch === '\\' && inString) {
      escape = true;
      continue;
    }
    if (ch === '"') {
      inString = !inString;
      continue;
    }
    if (inString) continue;
    if (ch === open) depth++;
    else if (ch === close) {
      depth--;
      if (depth === 0) return text.slice(start, i + 1);
    }
  }

  return null;
}

/**
 * LLM 응답 텍스트에서 JSON을 추출하고 파싱한다.
 * 3개 클라이언트 (ClaudeClient, ClaudeCliClient, LocalModelClient)의
 * chatJSON 메서드에서 공통으로 사용하여 DRY를 유지한다.
 */
export function parseJSONResponse<T>(content: string, source: string): T {
  const jsonStr = extractJSON(content);
  try {
    return JSON.parse(jsonStr) as T;
  } catch (err) {
    const preview = jsonStr.length > 200 ? jsonStr.slice(0, 200) + '...' : jsonStr;
    throw new Error(
      `Failed to parse ${source} JSON response: ${(err as Error).message}\nResponse preview: ${preview}`,
      { cause: err },
    );
  }
}
