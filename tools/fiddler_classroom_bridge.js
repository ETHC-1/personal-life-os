// Fiddler Classic: Rules > Customize Rules，将此逻辑加入 Handlers 类。
// 仅把空教室响应中的教室、课时、日期转发到本机；不转发 Cookie、token 或其他课程字段。
static function JsonEscape(value: String): String {
    return value.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", "\\r").Replace("\n", "\\n");
}

static function SanitizeClassroomResponse(body: String): String {
    var pattern: String = "\"jxcdmc\"\\s*:\\s*\"([^\"]*)\"[\\s\\S]*?\"jcdm2\"\\s*:\\s*\"([^\"]*)\"[\\s\\S]*?\"rq\"\\s*:\\s*\"([^\"]*)\"";
    var matches: System.Text.RegularExpressions.MatchCollection = System.Text.RegularExpressions.Regex.Matches(body, pattern);
    var items: System.Text.StringBuilder = new System.Text.StringBuilder();
    for (var match: System.Text.RegularExpressions.Match in matches) {
        if (items.Length > 0) items.Append(",");
        items.Append("{\"jxcdmc\":\"").Append(JsonEscape(match.Groups[1].Value));
        items.Append("\",\"jcdm2\":\"").Append(JsonEscape(match.Groups[2].Value));
        items.Append("\",\"rq\":\"").Append(JsonEscape(match.Groups[3].Value)).Append("\"}");
    }
    return "{\"jszylist\":[" + items.ToString() + "]}";
}

static function OnBeforeResponse(oSession: Session) {
    if (!oSession.HostnameIs("jwweb.hebmu.edu.cn")) return;
    if (!oSession.uriContains("/dev-api/appapi/appkxjs/classroom")) return;
    if (oSession.responseCode != 200) return;

    var body: String = SanitizeClassroomResponse(oSession.GetResponseBodyAsString());
    var client: System.Net.WebClient = new System.Net.WebClient();
    client.Headers.Add("Content-Type", "application/json; charset=utf-8");
    try {
        client.UploadString("http://127.0.0.1:8765/ingest", "POST", body);
    } catch (e) {
        FiddlerApplication.Log.LogString("classroom bridge failed: " + e);
    }
}
