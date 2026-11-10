package app.couchtv.launcher

import android.annotation.SuppressLint
import android.app.Activity
import android.graphics.Color
import android.net.Uri
import android.net.http.SslError
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.WindowManager
import android.webkit.SslErrorHandler
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.util.Calendar
import java.util.concurrent.Executors

/**
 * couch-tv-lab: the DisplayOS wall on the TV.
 *
 * The bridge turns DisplayOS's own config into a plan (GET /api/lab/wall): slides of one or two dashboards,
 * an interlude (clock, weather, verse) after every N slides, quiet hours, and certificate pins for
 * dashboards with a self-signed certificate. This screen follows it with two dashboard panes and one
 * interlude page. While an interlude is up, the panes load the next slide behind it, so a slide appears
 * already loaded and no more than two dashboards are ever in memory (the TV has 2 GB).
 *
 * Remote: left / right = previous / next, OK = pause, and while paused the D-pad and OK go to the page (to
 * log in or scroll); Back leaves pause, then the wall. "Show DisplayOS" (bridge: POST /api/lab/wall/show)
 * starts it with "resume", which continues where it stopped.
 */
class WallActivity : Activity() {
    private val main = Handler(Looper.getMainLooper())
    private val io = Executors.newSingleThreadExecutor()
    private val prefs by lazy { getSharedPreferences("wall", MODE_PRIVATE) }

    private lateinit var panes: LinearLayout
    private val paneViews = mutableListOf<WebView>()
    private val paneUrls = arrayOfNulls<String>(2)
    private val paneLoadedAt = LongArray(2)
    private lateinit var interlude: WebView
    private lateinit var status: TextView
    private lateinit var black: View

    private var plan: JSONObject? = null
    private var steps = listOf<Step>()
    private var index = 0
    private var remaining = 0
    private var paused = false
    private var quiet = false
    private var base: String? = null
    private var lastPlanAt = 0L

    private sealed class Step {
        data class Slide(val name: String, val ids: List<String>, val seconds: Int) : Step()
        data class Interlude(val type: String, val seconds: Int) : Step()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON or WindowManager.LayoutParams.FLAG_FULLSCREEN)
        val root = FrameLayout(this).apply { setBackgroundColor(Color.BLACK) }
        panes = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        repeat(2) {
            val w = makeWebView(it)
            paneViews += w
            panes.addView(w, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1f))
        }
        root.addView(panes, FrameLayout.LayoutParams(-1, -1))
        interlude = makeWebView(-1).apply { visibility = View.GONE }
        root.addView(interlude, FrameLayout.LayoutParams(-1, -1))
        black = View(this).apply { setBackgroundColor(Color.BLACK); visibility = View.GONE }
        root.addView(black, FrameLayout.LayoutParams(-1, -1))
        status = TextView(this).apply {
            setTextColor(Color.argb(220, 255, 255, 255)); textSize = 13f
            setBackgroundColor(Color.argb(150, 0, 0, 0)); setPadding(24, 8, 24, 8)
        }
        root.addView(status, FrameLayout.LayoutParams(-2, -2, Gravity.BOTTOM or Gravity.START).apply { setMargins(24, 0, 0, 20) })
        setContentView(root)
        @Suppress("DEPRECATION")
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_FULLSCREEN or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY

        base = getSharedPreferences("home", MODE_PRIVATE).getString("bridge", null) ?: BuildConfig.BRIDGES.firstOrNull()
        if (base == null) { status.text = "DisplayOS needs the bridge (option B)"; return }
        loadPlan(resume = intent.getBooleanExtra("resume", true))
        main.postDelayed(tick, 1000)
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun makeWebView(pane: Int): WebView = WebView(this).apply {
        setBackgroundColor(Color.BLACK)
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.useWideViewPort = true
        settings.loadWithOverviewMode = true
        settings.mediaPlaybackRequiresUserGesture = true
        isFocusable = true
        webViewClient = object : WebViewClient() {
            // dashboards navigate inside themselves (logins, redirects): stay in this view
            override fun shouldOverrideUrlLoading(view: WebView, req: WebResourceRequest) = false

            override fun onPageFinished(view: WebView, url: String) {
                if (pane >= 0) injectCss(view, pane)
            }

            // a self-signed dashboard is accepted only with the certificate the bridge pinned for its host
            override fun onReceivedSslError(view: WebView, handler: SslErrorHandler, error: SslError) {
                val uri = Uri.parse(error.url)
                val key = "${uri.host}:${if (uri.port > 0) uri.port else 443}"
                // only an untrusted (self-signed) issuer is ever overridden; expired, wrong host etc. never are
                val untrustedOnly = error.primaryError == SslError.SSL_UNTRUSTED
                // and only for a host that one of the plan's own dashboards points at
                val inPlan = plan?.optJSONObject("dashboards")?.let { ds -> ds.keys().asSequence().any { id ->
                    Uri.parse(ds.optJSONObject(id)?.optString("url").orEmpty()).let { u -> "${u.host}:${if (u.port > 0) u.port else 443}" == key } } } == true
                val want = plan?.optJSONObject("pins")?.optString(key, null)
                val got = if (Build.VERSION.SDK_INT >= 29) error.certificate.x509Certificate?.let { fingerprint(it.encoded) } else null
                if (untrustedOnly && inPlan && want != null && got != null && want.equals(got, ignoreCase = true)) handler.proceed()
                else { Log.w(TAG, "certificate refused for $key (error ${error.primaryError})"); handler.cancel() }
            }
        }
    }

    private fun fingerprint(der: ByteArray) = MessageDigest.getInstance("SHA-256").digest(der).joinToString("") { "%02X".format(it) }

    private fun injectCss(view: WebView, pane: Int) {
        val id = currentSlideIds().getOrNull(pane) ?: return
        val css = plan?.optJSONObject("dashboards")?.optJSONObject(id)?.optString("css", "").orEmpty()
        if (css.isBlank()) return
        view.evaluateJavascript("(function(){var s=document.createElement('style');s.textContent=${JSONObject.quote(css)};document.head.appendChild(s);})();", null)
    }

    private fun loadPlan(resume: Boolean) {
        val b = base ?: return
        io.execute {
            val j = runCatching {
                val c = URL("$b/api/lab/wall").openConnection() as HttpURLConnection
                c.connectTimeout = 6000; c.readTimeout = 10000
                c.inputStream.bufferedReader().use { JSONObject(it.readText()) }
            }.getOrNull()
            main.post {
                if (j == null || !j.optBoolean("ok")) {
                    if (plan == null) status.text = "DisplayOS: no plan from the bridge. Retrying…"
                    main.postDelayed({ loadPlan(resume) }, 30_000)
                    return@post
                }
                val first = plan == null
                plan = j; lastPlanAt = System.currentTimeMillis()
                steps = buildSteps(j)
                if (first) {
                    index = if (resume) prefs.getInt("index", 0).coerceIn(0, maxOf(0, steps.size - 1)) else 0
                    show(index)
                }
            }
        }
    }

    private fun buildSteps(j: JSONObject): List<Step> {
        val out = mutableListOf<Step>()
        val slides = j.optJSONArray("slides") ?: return out
        val inter = j.optJSONObject("interludes")
        val every = inter?.optInt("every", 0) ?: 0
        val items = inter?.optJSONArray("items")
        var k = 0
        for (i in 0 until slides.length()) {
            val s = slides.getJSONObject(i)
            val ids = s.getJSONArray("ids").let { a -> (0 until a.length()).map { a.getString(it) } }
            out += Step.Slide(s.optString("name"), ids, s.optInt("duration", 180))
            if (every > 0 && items != null && items.length() > 0 && (i + 1) % every == 0) {
                val it = items.getJSONObject(k++ % items.length())
                out += Step.Interlude(it.optString("type", "clock"), it.optInt("duration", 30))
            }
        }
        return out
    }

    private fun currentSlideIds(): List<String> = (steps.getOrNull(index) as? Step.Slide)?.ids ?: emptyList()

    private fun dashboard(id: String) = plan?.optJSONObject("dashboards")?.optJSONObject(id)

    /** Put a slide's dashboards in the panes (only reloading what changed or has gone stale). */
    private fun loadPanes(slide: Step.Slide) {
        for (p in 0 until 2) {
            val d = slide.ids.getOrNull(p)?.let { dashboard(it) }
            val view = paneViews[p]
            view.visibility = if (d != null) View.VISIBLE else View.GONE
            if (d == null) continue
            val url = d.optString("url")
            val zoom = d.optDouble("zoom", 1.0)
            view.settings.textZoom = (zoom * 100).toInt()
            val stale = d.optInt("refresh", 0) > 0 && System.currentTimeMillis() - paneLoadedAt[p] > d.optInt("refresh") * 1000L
            if (paneUrls[p] != url || stale) {
                paneUrls[p] = url; paneLoadedAt[p] = System.currentTimeMillis()
                view.loadUrl(url)
            }
        }
    }

    private fun show(i: Int) {
        if (steps.isEmpty()) { status.text = "DisplayOS: no slides"; return }
        index = ((i % steps.size) + steps.size) % steps.size
        prefs.edit().putInt("index", index).apply()
        when (val s = steps[index]) {
            is Step.Slide -> {
                loadPanes(s)
                interlude.visibility = View.GONE
                panes.visibility = View.VISIBLE
                remaining = s.seconds
            }
            is Step.Interlude -> {
                interlude.loadUrl("${base}/tv/wall/interlude.html?type=${s.type}")
                interlude.visibility = View.VISIBLE
                remaining = s.seconds
                // the next slide loads behind the interlude
                (steps.getOrNull((index + 1) % steps.size) as? Step.Slide)?.let { loadPanes(it) }
            }
        }
        drawStatus()
    }

    private fun drawStatus() {
        val s = steps.getOrNull(index)
        val name = when (s) { is Step.Slide -> s.name; is Step.Interlude -> s.type.replaceFirstChar { it.uppercase() }; null -> "" }
        val next = (steps.getOrNull((index + 1) % maxOf(1, steps.size)) as? Step.Slide)?.name
        val c = Calendar.getInstance()
        val clock = "%d:%02d".format(if (c.get(Calendar.HOUR) == 0) 12 else c.get(Calendar.HOUR), c.get(Calendar.MINUTE))
        status.text = when {
            quiet -> ""
            paused -> "$name · paused: arrows and OK use the page · Back to resume"
            else -> listOfNotNull(name, "${remaining}s", next?.let { "next: $it" }, clock).joinToString("  ·  ")
        }
        status.visibility = if (quiet) View.GONE else View.VISIBLE
    }

    private fun inQuietHours(): Boolean {
        val q = plan?.optJSONObject("quiet") ?: return false
        fun mins(t: String) = t.split(":").let { if (it.size == 2) it[0].toIntOrNull()?.times(60)?.plus(it[1].toIntOrNull() ?: 0) else null }
        val start = mins(q.optString("start")) ?: return false
        val end = mins(q.optString("end")) ?: return false
        val c = Calendar.getInstance(); val now = c.get(Calendar.HOUR_OF_DAY) * 60 + c.get(Calendar.MINUTE)
        return if (start <= end) now in start until end else now >= start || now < end
    }

    private val tick = object : Runnable {
        override fun run() {
            val q = inQuietHours()
            if (q != quiet) {
                quiet = q
                black.visibility = if (q) View.VISIBLE else View.GONE
                if (q) window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) else window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            }
            if (!paused && !quiet && steps.isNotEmpty() && --remaining <= 0) show(index + 1)
            drawStatus()
            if (System.currentTimeMillis() - lastPlanAt > 10 * 60_000) loadPlan(resume = true)   // config changes on the Mac
            main.postDelayed(this, 1000)
        }
    }

    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (paused && event.keyCode != KeyEvent.KEYCODE_BACK) {
            // paused: the remote drives the page itself (log in, scroll)
            val target = paneViews.firstOrNull { it.visibility == View.VISIBLE && panes.visibility == View.VISIBLE }
            if (target != null && !target.hasFocus()) target.requestFocus()
            return super.dispatchKeyEvent(event)
        }
        if (event.action != KeyEvent.ACTION_UP) return when (event.keyCode) {
            KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_BACK -> true
            else -> super.dispatchKeyEvent(event)
        }
        when (event.keyCode) {
            KeyEvent.KEYCODE_DPAD_RIGHT -> show(index + 1)
            KeyEvent.KEYCODE_DPAD_LEFT -> show(index - 1)
            KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER -> { paused = true; drawStatus() }
            KeyEvent.KEYCODE_BACK -> if (paused) { paused = false; panes.requestFocus(); drawStatus() } else finish()
            else -> return super.dispatchKeyEvent(event)
        }
        return true
    }

    override fun onNewIntent(intent: android.content.Intent) {
        super.onNewIntent(intent)
        paused = false
        drawStatus()
    }

    override fun onDestroy() {
        main.removeCallbacksAndMessages(null)
        (paneViews + interlude).forEach { runCatching { it.destroy() } }
        io.shutdownNow()
        super.onDestroy()
    }

    companion object { private const val TAG = "couchtv.wall" }
}
