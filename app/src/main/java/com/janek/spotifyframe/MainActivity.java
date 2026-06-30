package com.janek.spotifyframe;

import android.app.Activity;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.SystemClock;
import android.view.MotionEvent;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.widget.ImageView;
import android.widget.ImageButton;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;

public class MainActivity extends Activity {
    private static final String BACKEND_BASE_URL = BuildConfig.BACKEND_BASE_URL;
    private static final String NOW_PLAYING_URL = BACKEND_BASE_URL + "/api/now";
    private static final String CONTROL_URL = BACKEND_BASE_URL + "/api/control";
    private static final long POLL_INTERVAL_MS = 2000L;
    private static final long PROGRESS_TICK_MS = 1000L;
    private static final long STATUS_MESSAGE_MS = 2500L;

    private final Handler handler = new Handler();
    private TextView titleText;
    private TextView artistText;
    private TextView albumText;
    private TextView stateText;
    private TextView progressStartText;
    private TextView progressEndText;
    private TextView coverPlaceholderText;
    private TextView statusOverlayText;
    private ImageView coverImageView;
    private ProgressBar progressBar;
    private LinearLayout progressLayout;
    private ImageButton previousButton;
    private ImageButton playPauseButton;
    private ImageButton nextButton;

    private boolean requestInFlight;
    private boolean coverRequestInFlight;
    private boolean controlRequestInFlight;
    private boolean canControl = true;
    private boolean hasSuccessfulData;
    private boolean showNothingPlayingState;
    private boolean shouldAnimateProgress;
    private boolean isCurrentlyPlaying;
    private long currentProgressMs;
    private long currentDurationMs;
    private long progressBaseElapsedMs;
    private String currentCoverUrl;
    private String pendingCoverUrl;
    private String controlUnavailableReason;
    private Bitmap currentCoverBitmap;
    private final Runnable hideStatusRunnable = new Runnable() {
        @Override
        public void run() {
            statusOverlayText.setVisibility(View.GONE);
        }
    };
    private final Runnable hideSystemUiRunnable = new Runnable() {
        @Override
        public void run() {
            hideSystemUi();
        }
    };

    private final Runnable pollRunnable = new Runnable() {
        @Override
        public void run() {
            hideSystemUi();
            if (!requestInFlight) {
                fetchNowPlaying();
            }
            handler.postDelayed(this, POLL_INTERVAL_MS);
        }
    };

    private final Runnable progressRunnable = new Runnable() {
        @Override
        public void run() {
            updateProgressUi();
            handler.postDelayed(this, PROGRESS_TICK_MS);
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN
                | WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        setContentView(R.layout.activity_main);

        titleText = (TextView) findViewById(R.id.titleText);
        artistText = (TextView) findViewById(R.id.artistText);
        albumText = (TextView) findViewById(R.id.albumText);
        stateText = (TextView) findViewById(R.id.stateText);
        progressStartText = (TextView) findViewById(R.id.progressStartText);
        progressEndText = (TextView) findViewById(R.id.progressEndText);
        coverPlaceholderText = (TextView) findViewById(R.id.coverPlaceholderText);
        statusOverlayText = (TextView) findViewById(R.id.statusOverlayText);
        coverImageView = (ImageView) findViewById(R.id.coverImageView);
        progressBar = (ProgressBar) findViewById(R.id.progressBar);
        progressLayout = (LinearLayout) findViewById(R.id.progressLayout);
        previousButton = (ImageButton) findViewById(R.id.previousButton);
        playPauseButton = (ImageButton) findViewById(R.id.playPauseButton);
        nextButton = (ImageButton) findViewById(R.id.nextButton);

        previousButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                if (!canControl) {
                    showTemporaryStatus(valueOrFallback(
                            controlUnavailableReason,
                            getString(R.string.control_auth_needed)
                    ));
                    return;
                }
                sendControlCommand("previous");
            }
        });
        playPauseButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                if (!canControl) {
                    showTemporaryStatus(valueOrFallback(
                            controlUnavailableReason,
                            getString(R.string.control_auth_needed)
                    ));
                    return;
                }
                sendControlCommand(isCurrentlyPlaying ? "pause" : "play");
            }
        });
        nextButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                if (!canControl) {
                    showTemporaryStatus(valueOrFallback(
                            controlUnavailableReason,
                            getString(R.string.control_auth_needed)
                    ));
                    return;
                }
                sendControlCommand("next");
            }
        });

        View decorView = getWindow().getDecorView();
        decorView.setOnSystemUiVisibilityChangeListener(new View.OnSystemUiVisibilityChangeListener() {
            @Override
            public void onSystemUiVisibilityChange(int visibility) {
                scheduleSystemUiHide(120L);
            }
        });

        showInitialState();
    }

    @Override
    protected void onResume() {
        super.onResume();
        hideSystemUi();
        handler.removeCallbacks(pollRunnable);
        handler.removeCallbacks(progressRunnable);
        handler.post(pollRunnable);
        handler.post(progressRunnable);
    }

    @Override
    protected void onPause() {
        super.onPause();
        handler.removeCallbacks(pollRunnable);
        handler.removeCallbacks(progressRunnable);
        handler.removeCallbacks(hideSystemUiRunnable);
    }

    @Override
    public boolean dispatchTouchEvent(MotionEvent event) {
        if (event != null) {
            int action = event.getActionMasked();
            if (action == MotionEvent.ACTION_DOWN
                    || action == MotionEvent.ACTION_MOVE
                    || action == MotionEvent.ACTION_UP) {
                scheduleSystemUiHide(80L);
            }
        }
        return super.dispatchTouchEvent(event);
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {
            hideSystemUi();
        }
    }

    private void hideSystemUi() {
        View decorView = getWindow().getDecorView();
        int flags = View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_FULLSCREEN;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT) {
            flags |= View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY;
        }
        decorView.setSystemUiVisibility(flags);
    }

    private void scheduleSystemUiHide(long delayMs) {
        handler.removeCallbacks(hideSystemUiRunnable);
        if (delayMs <= 0L) {
            hideSystemUi();
            return;
        }
        handler.postDelayed(hideSystemUiRunnable, delayMs);
    }

    private void fetchNowPlaying() {
        requestInFlight = true;
        new Thread(new Runnable() {
            @Override
            public void run() {
                HttpURLConnection connection = null;
                int responseCode = -1;

                try {
                    URL url = new URL(NOW_PLAYING_URL);
                    connection = (HttpURLConnection) url.openConnection();
                    connection.setRequestMethod("GET");
                    connection.setConnectTimeout(2000);
                    connection.setReadTimeout(2000);
                    connection.setUseCaches(false);

                    responseCode = connection.getResponseCode();
                    if (responseCode != HttpURLConnection.HTTP_OK) {
                        throw new IllegalStateException("HTTP " + responseCode);
                    }

                    String body = readAll(connection.getInputStream());
                    final NowPlayingPayload payload = parsePayload(body);

                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            applyPayload(payload);
                        }
                    });
                } catch (final Exception exception) {
                    final String errorMessage = formatException(exception, responseCode);
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            handleBackendUnavailable(errorMessage);
                        }
                    });
                } finally {
                    if (connection != null) {
                        connection.disconnect();
                    }
                    requestInFlight = false;
                }
            }
        }).start();
    }

    private NowPlayingPayload parsePayload(String body) throws Exception {
        JSONObject json = new JSONObject(body);
        if (!json.optBoolean("ok", false)) {
            throw new IllegalStateException(valueOrFallback(
                    json.optString("error"),
                    "Backend returned ok=false"
            ));
        }

        NowPlayingPayload payload = new NowPlayingPayload();
        payload.title = valueOrFallback(json.optString("title"), getString(R.string.unknown_title));
        payload.artist = safeString(json.optString("artist"));
        payload.album = safeString(json.optString("album"));
        payload.playing = json.optBoolean("playing", false);
        payload.progressMs = Math.max(0L, json.optLong("progress_ms", 0L));
        payload.durationMs = Math.max(0L, json.optLong("duration_ms", 0L));
        payload.coverUrl = json.isNull("cover_url") ? null : safeString(json.optString("cover_url"));
        payload.canControl = json.optBoolean("can_control", true);
        payload.controlUnavailableReason = json.isNull("control_unavailable_reason")
                ? null
                : safeString(json.optString("control_unavailable_reason"));
        payload.isNothingPlaying = !payload.playing
                && payload.durationMs <= 0L
                && payload.coverUrl == null
                && payload.artist.length() == 0
                && payload.album.length() == 0;
        return payload;
    }

    private void applyPayload(NowPlayingPayload payload) {
        hasSuccessfulData = true;
        showNothingPlayingState = payload.isNothingPlaying;
        shouldAnimateProgress = payload.playing && payload.durationMs > 0L;
        isCurrentlyPlaying = payload.playing;
        canControl = payload.canControl;
        controlUnavailableReason = payload.controlUnavailableReason;
        currentProgressMs = payload.progressMs;
        currentDurationMs = payload.durationMs;
        progressBaseElapsedMs = SystemClock.elapsedRealtime();

        titleText.setText(payload.title);
        bindSecondaryText(artistText, payload.artist);
        bindSecondaryText(albumText, payload.album);

        if (payload.isNothingPlaying) {
            stateText.setVisibility(View.GONE);
            progressLayout.setVisibility(View.GONE);
        } else {
            stateText.setText(payload.playing ? R.string.playing_label : R.string.paused_label);
            stateText.setTextColor(getResources().getColor(
                    payload.playing ? R.color.state_text : R.color.paused_text
            ));
            stateText.setVisibility(View.VISIBLE);
            progressLayout.setVisibility(payload.durationMs > 0L ? View.VISIBLE : View.GONE);
        }

        updateProgressUi();
        bindCover(payload.coverUrl);
        updateControlUi();
        hideStatusOverlay();
    }

    private void handleBackendUnavailable(String errorMessage) {
        statusOverlayText.setTag(errorMessage);
        shouldAnimateProgress = false;
        updateProgressUi();
        updateControlUi();

        if (!hasSuccessfulData) {
            showInitialState();
            statusOverlayText.setText(R.string.waiting_overlay);
        } else {
            statusOverlayText.setText(R.string.reconnecting_overlay);
        }

        statusOverlayText.setVisibility(View.VISIBLE);
    }

    private void showInitialState() {
        titleText.setText(R.string.waiting_title);
        bindSecondaryText(artistText, "");
        bindSecondaryText(albumText, "");
        stateText.setVisibility(View.GONE);
        progressLayout.setVisibility(View.GONE);
        shouldAnimateProgress = false;
        isCurrentlyPlaying = false;
        canControl = true;
        controlUnavailableReason = null;
        currentProgressMs = 0L;
        currentDurationMs = 0L;
        showNothingPlayingState = true;
        clearCover();
        updateControlUi();
        hideStatusOverlay();
    }

    private void hideStatusOverlay() {
        handler.removeCallbacks(hideStatusRunnable);
        statusOverlayText.setVisibility(View.GONE);
    }

    private void showTemporaryStatus(String message) {
        statusOverlayText.setText(message);
        statusOverlayText.setVisibility(View.VISIBLE);
        handler.removeCallbacks(hideStatusRunnable);
        handler.postDelayed(hideStatusRunnable, STATUS_MESSAGE_MS);
    }

    private void updateControlUi() {
        previousButton.setEnabled(true);
        playPauseButton.setEnabled(true);
        nextButton.setEnabled(true);
        playPauseButton.setImageResource(
                isCurrentlyPlaying ? R.drawable.ic_control_pause : R.drawable.ic_control_play
        );
        playPauseButton.setContentDescription(getString(
                isCurrentlyPlaying ? R.string.control_pause_desc : R.string.control_play_desc
        ));
        float disabledAlpha = controlRequestInFlight ? 0.45f : (canControl ? 1.0f : 0.35f);
        previousButton.setAlpha(disabledAlpha);
        playPauseButton.setAlpha(disabledAlpha);
        nextButton.setAlpha(disabledAlpha);
    }

    private void bindSecondaryText(TextView textView, String value) {
        if (value == null || value.trim().length() == 0) {
            textView.setText("");
            textView.setVisibility(View.GONE);
            return;
        }
        textView.setText(value);
        textView.setVisibility(View.VISIBLE);
    }

    private void bindCover(String coverUrl) {
        if (coverUrl == null || coverUrl.trim().length() == 0) {
            clearCover();
            return;
        }

        if (coverUrl.equals(currentCoverUrl) && currentCoverBitmap != null) {
            coverImageView.setImageBitmap(currentCoverBitmap);
            coverPlaceholderText.setVisibility(View.GONE);
            return;
        }

        if (coverRequestInFlight && coverUrl.equals(pendingCoverUrl)) {
            return;
        }

        coverPlaceholderText.setVisibility(View.VISIBLE);
        coverImageView.setImageDrawable(null);
        fetchCoverBitmap(coverUrl);
    }

    private void fetchCoverBitmap(final String coverUrl) {
        coverRequestInFlight = true;
        pendingCoverUrl = coverUrl;

        new Thread(new Runnable() {
            @Override
            public void run() {
                HttpURLConnection connection = null;
                try {
                    URL url = new URL(coverUrl);
                    connection = (HttpURLConnection) url.openConnection();
                    connection.setRequestMethod("GET");
                    connection.setConnectTimeout(3000);
                    connection.setReadTimeout(5000);
                    connection.setUseCaches(false);

                    int responseCode = connection.getResponseCode();
                    if (responseCode != HttpURLConnection.HTTP_OK) {
                        throw new IllegalStateException("Cover HTTP " + responseCode);
                    }

                    byte[] bytes = readBytes(connection.getInputStream());
                    final Bitmap bitmap = decodeCoverBitmap(bytes);
                    if (bitmap == null) {
                        throw new IllegalStateException("Cover decode failed");
                    }

                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            if (!coverUrl.equals(pendingCoverUrl)) {
                                return;
                            }
                            currentCoverUrl = coverUrl;
                            currentCoverBitmap = bitmap;
                            coverImageView.setImageBitmap(bitmap);
                            coverPlaceholderText.setVisibility(View.GONE);
                        }
                    });
                } catch (Exception ignored) {
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            if (coverUrl.equals(pendingCoverUrl) && currentCoverBitmap == null) {
                                clearCover();
                            }
                        }
                    });
                } finally {
                    if (connection != null) {
                        connection.disconnect();
                    }
                    if (coverUrl.equals(pendingCoverUrl)) {
                        coverRequestInFlight = false;
                    }
                }
            }
        }).start();
    }

    private void clearCover() {
        currentCoverUrl = null;
        currentCoverBitmap = null;
        pendingCoverUrl = null;
        coverRequestInFlight = false;
        coverImageView.setImageDrawable(null);
        coverPlaceholderText.setVisibility(View.VISIBLE);
    }

    private void sendControlCommand(final String action) {
        if (controlRequestInFlight) {
            return;
        }
        if (!canControl) {
            showTemporaryStatus(valueOrFallback(
                    controlUnavailableReason,
                    getString(R.string.control_auth_needed)
            ));
            return;
        }

        controlRequestInFlight = true;
        updateControlUi();

        new Thread(new Runnable() {
            @Override
            public void run() {
                HttpURLConnection connection = null;
                int responseCode = -1;

                try {
                    URL url = new URL(CONTROL_URL);
                    connection = (HttpURLConnection) url.openConnection();
                    connection.setRequestMethod("POST");
                    connection.setConnectTimeout(2000);
                    connection.setReadTimeout(3000);
                    connection.setUseCaches(false);
                    connection.setDoOutput(true);
                    connection.setRequestProperty("Content-Type", "application/json; charset=UTF-8");

                    OutputStream outputStream = connection.getOutputStream();
                    try {
                        byte[] payload = ("{\"action\":\"" + action + "\"}").getBytes("UTF-8");
                        outputStream.write(payload);
                    } finally {
                        outputStream.close();
                    }

                    responseCode = connection.getResponseCode();
                    String body = readAll(responseCode >= 400
                            ? connection.getErrorStream()
                            : connection.getInputStream());

                    JSONObject json = new JSONObject(body);
                    if (responseCode != HttpURLConnection.HTTP_OK || !json.optBoolean("ok", false)) {
                        throw new IllegalStateException(valueOrFallback(
                                json.optString("error"),
                                "Control request failed"
                        ));
                    }

                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            controlRequestInFlight = false;
                            if ("play".equals(action)) {
                                isCurrentlyPlaying = true;
                            } else if ("pause".equals(action)) {
                                isCurrentlyPlaying = false;
                            }
                            updateControlUi();
                            handler.postDelayed(new Runnable() {
                                @Override
                                public void run() {
                                    if (!requestInFlight) {
                                        fetchNowPlaying();
                                    }
                                }
                            }, 250L);
                        }
                    });
                } catch (final Exception exception) {
                    final String errorMessage = formatControlError(exception, responseCode);
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            controlRequestInFlight = false;
                            updateControlUi();
                            showTemporaryStatus(errorMessage);
                        }
                    });
                } finally {
                    if (connection != null) {
                        connection.disconnect();
                    }
                }
            }
        }).start();
    }

    private void updateProgressUi() {
        if (showNothingPlayingState || currentDurationMs <= 0L) {
            progressLayout.setVisibility(View.GONE);
            return;
        }

        progressLayout.setVisibility(View.VISIBLE);
        long progress = currentProgressMs;
        if (shouldAnimateProgress) {
            long elapsed = SystemClock.elapsedRealtime() - progressBaseElapsedMs;
            progress = Math.min(currentDurationMs, currentProgressMs + elapsed);
        }

        progressBar.setMax((int) Math.max(1L, currentDurationMs));
        progressBar.setProgress((int) Math.max(0L, progress));
        progressStartText.setText(formatDuration(progress));
        progressEndText.setText(formatDuration(currentDurationMs));
    }

    private Bitmap decodeCoverBitmap(byte[] bytes) {
        BitmapFactory.Options bounds = new BitmapFactory.Options();
        bounds.inJustDecodeBounds = true;
        BitmapFactory.decodeByteArray(bytes, 0, bytes.length, bounds);

        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inPreferredConfig = Bitmap.Config.RGB_565;
        options.inSampleSize = calculateInSampleSize(bounds, 512, 512);
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.length, options);
    }

    private int calculateInSampleSize(BitmapFactory.Options options, int reqWidth, int reqHeight) {
        int height = options.outHeight;
        int width = options.outWidth;
        int inSampleSize = 1;

        while ((height / inSampleSize) > reqHeight || (width / inSampleSize) > reqWidth) {
            inSampleSize *= 2;
        }

        return Math.max(1, inSampleSize);
    }

    private byte[] readBytes(InputStream inputStream) throws Exception {
        ByteArrayOutputStream outputStream = new ByteArrayOutputStream();
        byte[] buffer = new byte[4096];
        int count;
        try {
            while ((count = inputStream.read(buffer)) != -1) {
                outputStream.write(buffer, 0, count);
            }
            return outputStream.toByteArray();
        } finally {
            inputStream.close();
            outputStream.close();
        }
    }

    private String readAll(InputStream inputStream) throws Exception {
        if (inputStream == null) {
            return "";
        }
        BufferedReader reader = new BufferedReader(new InputStreamReader(inputStream, "UTF-8"));
        try {
            StringBuilder builder = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                builder.append(line);
            }
            return builder.toString();
        } finally {
            reader.close();
        }
    }

    private String formatDuration(long durationMs) {
        long totalSeconds = Math.max(0L, durationMs / 1000L);
        long hours = totalSeconds / 3600L;
        long minutes = (totalSeconds % 3600L) / 60L;
        long seconds = totalSeconds % 60L;

        if (hours > 0L) {
            return hours + ":" + padNumber(minutes) + ":" + padNumber(seconds);
        }
        return minutes + ":" + padNumber(seconds);
    }

    private String padNumber(long value) {
        return value < 10L ? "0" + value : String.valueOf(value);
    }

    private String formatException(Exception exception, int responseCode) {
        StringBuilder builder = new StringBuilder();
        if (responseCode >= 0) {
            builder.append("HTTP ").append(responseCode);
        }

        String message = exception.getMessage();
        if (message != null && message.trim().length() > 0) {
            if (builder.length() > 0) {
                builder.append(" | ");
            }
            builder.append(message.trim());
        }

        if (builder.length() == 0) {
            builder.append(exception.getClass().getName());
        }
        return builder.toString();
    }

    private String formatControlError(Exception exception, int responseCode) {
        String message = exception.getMessage();
        if (message != null) {
            String trimmed = message.trim();
            String normalized = trimmed.toLowerCase();
            if (normalized.contains("playback control not authorized")
                    || normalized.contains("authorization missing")
                    || normalized.contains("authorize.py")
                    || normalized.contains("user-modify-playback-state")) {
                return getString(R.string.control_auth_needed);
            }
            if (trimmed.length() > 0 && responseCode < 400) {
                return trimmed;
            }
        }
        return formatException(exception, responseCode);
    }

    private String safeString(String value) {
        if (value == null) {
            return "";
        }
        String trimmed = value.trim();
        return trimmed.length() == 0 ? "" : trimmed;
    }

    private String valueOrFallback(String value, String fallback) {
        String safeValue = safeString(value);
        if (safeValue.length() == 0) {
            return fallback;
        }
        return safeValue;
    }

    private static class NowPlayingPayload {
        String title;
        String artist;
        String album;
        boolean playing;
        boolean isNothingPlaying;
        boolean canControl;
        long progressMs;
        long durationMs;
        String coverUrl;
        String controlUnavailableReason;
    }
}
