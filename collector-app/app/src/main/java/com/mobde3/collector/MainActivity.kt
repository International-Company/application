package com.mobde3.collector

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.provider.Settings as AndroidSettings
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

/**
 * شاشة إعداد واحدة على هاتف الشركة.
 *
 * لا يستعملها إلا فريق التشغيل مرة واحدة عند التجهيز: عنوان الخادم، ومعرّف
 * الجهاز وسرّه، وحساب الاستلام، ومرسِلو البنك المسموح بهم.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var settings: Settings

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        settings = Settings(this)

        val baseUrl = findViewById<EditText>(R.id.baseUrl)
        val collectorId = findViewById<EditText>(R.id.collectorId)
        val secret = findViewById<EditText>(R.id.secret)
        val account = findViewById<EditText>(R.id.account)
        val senders = findViewById<EditText>(R.id.senders)
        val status = findViewById<TextView>(R.id.status)

        baseUrl.setText(settings.baseUrl)
        collectorId.setText(settings.collectorId)
        account.setText(settings.accountIdentifier)
        senders.setText(settings.allowedSenders)

        findViewById<Button>(R.id.save).setOnClickListener {
            settings.baseUrl = baseUrl.text.toString()
            settings.collectorId = collectorId.text.toString()
            if (secret.text.isNotBlank()) settings.secret = secret.text.toString()
            settings.accountIdentifier = account.text.toString()
            settings.allowedSenders = senders.text.toString()
            secret.setText("")
            status.text = statusText()
            Toast.makeText(this, R.string.saved, Toast.LENGTH_SHORT).show()
        }

        findViewById<Button>(R.id.grantSms).setOnClickListener { requestSmsPermission() }

        findViewById<Button>(R.id.grantNotifications).setOnClickListener {
            startActivity(Intent(AndroidSettings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
        }

        status.text = statusText()
    }

    private fun statusText(): String {
        val configured = if (settings.isConfigured) R.string.ready else R.string.not_ready
        val smsGranted = ContextCompat.checkSelfPermission(this, Manifest.permission.RECEIVE_SMS) ==
            PackageManager.PERMISSION_GRANTED
        val smsLabel = getString(if (smsGranted) R.string.granted else R.string.missing)
        return "${getString(configured)}\n${getString(R.string.sms_permission)}: $smsLabel"
    }

    private fun requestSmsPermission() {
        ActivityCompat.requestPermissions(
            this,
            arrayOf(Manifest.permission.RECEIVE_SMS, Manifest.permission.READ_SMS),
            REQUEST_SMS,
        )
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        findViewById<TextView>(R.id.status).text = statusText()
    }

    private companion object {
        const val REQUEST_SMS = 1001
    }
}
